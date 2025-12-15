"""Authentication service handling manual and OAuth flows with enhanced security."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.configs import settings
from app.errors.auth import (
    AccountLockedError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    TokenRevokedError,
    UserDeactivatedError,
    UserNotFoundError,
)
from app.managers.login_attempt_tracker import LoginAttemptTracker
from app.managers.password_manager import hash_password, verify_password
from app.managers.token_blacklist import TokenBlacklist
from app.managers.token_manager import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_token_expiry,
    get_token_jti,
)
from app.models import UserDB
from app.repositories import UserRepository
from app.schemas.auth import Token
from app.schemas.user import UserCreate


class AuthService:
    """Service for handling user authentication with enhanced security."""

    def __init__(
        self,
        user_repo: UserRepository,
        token_blacklist: TokenBlacklist | None = None,
        login_tracker: LoginAttemptTracker | None = None,
    ) -> None:
        """
        Initialize the auth service.

        Args:
            user_repo: User repository for database operations
            token_blacklist: Optional token blacklist for revocation
            login_tracker: Optional login attempt tracker for brute-force protection
        """
        self.user_repo = user_repo
        self._blacklist = token_blacklist
        self._login_tracker = login_tracker

    async def _check_lockout(self, identifier: str) -> None:
        """Check if user is locked out and raise if so."""
        if not self._login_tracker:
            return
        is_locked, seconds_remaining = await self._login_tracker.is_locked_out(identifier)
        if is_locked:
            raise AccountLockedError(seconds_remaining=seconds_remaining)

    async def _record_failed_attempt(self, identifier: str) -> None:
        """Record a failed login attempt if tracker is available."""
        if self._login_tracker:
            await self._login_tracker.record_failed_attempt(identifier)

    async def _get_user_by_identifier(self, identifier: str) -> UserDB | None:
        """Get user by username or email."""
        if "@" in identifier:
            return await self.user_repo.get_by_email(identifier)
        return await self.user_repo.get_by_username(identifier)

    async def authenticate_user(self, username_or_email: str, password: str | None) -> UserDB:
        """
        Authenticate a user by username or email and password.

        Args:
            username_or_email: User username or email
            password: User password

        Returns:
            UserDB: Authenticated user

        Raises:
            AccountLockedError: If account is locked due to failed attempts
            InvalidCredentialsError: If authentication fails
        """
        await self._check_lockout(username_or_email)

        user = await self._get_user_by_identifier(username_or_email)
        if not user or not user.password_hash or not password:
            await self._record_failed_attempt(username_or_email)
            raise InvalidCredentialsError

        if not await verify_password(password, user.password_hash):
            await self._record_failed_attempt(username_or_email)
            raise InvalidCredentialsError

        # Reset failed attempts on successful login
        if self._login_tracker:
            await self._login_tracker.reset_attempts(username_or_email)

        return user

    def create_token_for_user(self, user: UserDB) -> Token:
        """
        Create access and refresh tokens for a user.

        Args:
            user: User entity

        Returns:
            Token: Token object with access and refresh tokens
        """
        access_token = create_access_token(
            user_id=user.uuid,
            username=user.username,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )

        refresh_token = create_refresh_token(
            user_id=user.uuid,
            username=user.username,
            expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )

    async def refresh_tokens(self, refresh_token: str) -> Token:
        """
        Exchange a refresh token for a new token pair (token rotation).

        Args:
            refresh_token: The refresh token to exchange

        Returns:
            Token: New token pair

        Raises:
            InvalidTokenError: If refresh token is invalid
            TokenExpiredError: If refresh token is expired
            UserNotFoundError: If user no longer exists
        """
        # Decode and validate refresh token
        token_data = decode_refresh_token(refresh_token)
        if not token_data:
            raise InvalidRefreshTokenError

        # Check if token is blacklisted
        if self._blacklist:
            is_blacklisted = await self._blacklist.is_blacklisted(token_data.jti)
            if is_blacklisted:
                raise TokenRevokedError

        # Get user
        user = await self.user_repo.get_by_id(token_data.user_id)
        if not user:
            raise UserNotFoundError

        if not user.is_active:
            raise UserDeactivatedError

        # Blacklist the old refresh token (token rotation)
        if self._blacklist:
            exp = get_token_expiry(refresh_token)
            if exp:
                await self._blacklist.add_to_blacklist(token_data.jti, exp)

        # Create new token pair
        return self.create_token_for_user(user)

    async def logout_user(self, access_token: str, refresh_token: str | None = None) -> bool:
        """
        Logout user by blacklisting tokens.

        Args:
            access_token: The access token to blacklist
            refresh_token: Optional refresh token to blacklist

        Returns:
            bool: True if successfully logged out
        """
        if not self._blacklist:
            return True  # No blacklist, logout is a no-op

        success = True

        # Blacklist access token
        access_jti = get_token_jti(access_token)
        access_exp = get_token_expiry(access_token)
        if access_jti and access_exp:
            result = await self._blacklist.add_to_blacklist(access_jti, access_exp)
            success = success and result

        # Blacklist refresh token if provided
        if refresh_token:
            refresh_jti = get_token_jti(refresh_token)
            refresh_exp = get_token_expiry(refresh_token)
            if refresh_jti and refresh_exp:
                result = await self._blacklist.add_to_blacklist(refresh_jti, refresh_exp)
                success = success and result

        return success

    async def send_verification_email(self, user: UserDB) -> str:
        """
        Generate email verification token for a user.

        Args:
            user: User to send verification email to

        Returns:
            str: Verification token (for email sending)
        """
        # Create a short-lived verification token (24 hours)
        verification_token = create_access_token(
            user_id=user.uuid,
            username=user.username,
            expires_delta=timedelta(hours=24),
        )
        # In production, this would send an actual email
        # For now, return the token for the route to handle email sending
        return verification_token

    async def verify_email(self, user_id: UUID) -> bool:
        """
        Mark user email as verified.

        Args:
            user_id: User UUID

        Returns:
            bool: True if successfully verified
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return False

        # Update user verification status directly
        user.is_verified = True
        user.updated_at = datetime.now(UTC)
        await self.user_repo._add_and_refresh(user)  # noqa: SLF001
        return True

    async def send_password_reset(self, email: str) -> str | None:
        """
        Generate password reset token for a user.

        Args:
            email: User email address

        Returns:
            str | None: Reset token if user exists, None otherwise
        """
        user = await self.user_repo.get_by_email(email)
        if not user:
            return None

        # Create a short-lived reset token (1 hour)
        reset_token = create_access_token(
            user_id=user.uuid,
            username=user.username,
            expires_delta=timedelta(hours=1),
        )
        return reset_token

    async def reset_password(self, user_id: UUID, new_password: str) -> bool:
        """
        Reset user password.

        Args:
            user_id: User UUID
            new_password: New password to set

        Returns:
            bool: True if successfully reset
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return False

        # Hash the new password
        password_hash = await hash_password(new_password)
        user.password_hash = password_hash
        user.updated_at = datetime.now(UTC)
        await self.user_repo._add_and_refresh(user)  # noqa: SLF001

        return True

    async def get_or_create_oauth_user(
        self,
        user_info: dict[str, Any],
        provider: str,
    ) -> UserDB:
        """
        Get existing user or create new one from OAuth data.

        Args:
            user_info: Dictionary containing user info from provider
            provider: Provider name (google, wechat)

        Returns:
            UserDB: The user entity
        """
        email = user_info.get("email")
        if not email:
            msg = "Email required from identity provider"
            raise ValueError(msg)

        existing_user = await self.user_repo.get_by_email(email)
        if existing_user:
            return existing_user

        # Create new user with unique username
        base_username = email.split("@")[0]
        random_suffix = str(uuid4())[:4]
        final_username = f"{base_username}_{random_suffix}"

        user_create = UserCreate(
            userName=final_username,
            email=email,
            password=None,
            firstName=user_info.get("given_name"),
            lastName=user_info.get("family_name"),
            profilePicture=user_info.get("picture"),
            isVerified=True,  # OAuth emails are usually verified
        )

        return await self.user_repo.create(
            user_create,
            auth_provider=provider,
            provider_id=user_info.get("sub"),
        )
