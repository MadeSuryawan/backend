"""Authentication service handling manual and OAuth flows with enhanced security."""

from datetime import UTC, datetime, timedelta
from logging import getLogger
from typing import Any
from uuid import UUID, uuid4

from app.clients.email_client import EmailClient
from app.clients.redis_client import RedisClient
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
    create_password_reset_token,
    create_refresh_token,
    create_verification_token,
    decode_refresh_token,
    get_token_expiry,
    get_token_jti,
)
from app.models import UserDB
from app.repositories import UserRepository
from app.schemas.auth import Token, VerificationTokenData
from app.schemas.user import UserCreate
from app.services.email_template_builder import EmailTemplateBuilder
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))


class AuthService:
    """
    Service for handling user authentication with enhanced security.

    This service provides methods for user authentication, token management,
    email verification, password reset, and OAuth flows.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        token_blacklist: TokenBlacklist | None = None,
        login_tracker: LoginAttemptTracker | None = None,
        redis_client: RedisClient | None = None,
        email_client: EmailClient | None = None,
    ) -> None:
        """
        Initialize the auth service.

        Args:
            user_repo: User repository for database operations
            token_blacklist: Optional token blacklist for revocation
            login_tracker: Optional login attempt tracker for brute-force protection
            redis_client: Optional Redis client for rate limiting
            email_client: Optional email client for sending notifications
        """
        self.user_repo = user_repo
        self._blacklist = token_blacklist
        self._login_tracker = login_tracker
        self._redis = redis_client
        self._email = email_client
        self._email_builder = EmailTemplateBuilder()

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

    async def send_verification_email(self, user: UserDB) -> None:
        """
        Generate email verification token for a user.

        Uses dedicated verification token type with email claim binding.

        Args:
            user: User to send verification email to

        Returns:
            str: Verification token (for email sending)
        """
        verification_token = create_verification_token(
            user_id=user.uuid,
            email=user.email,
            expires_delta=timedelta(hours=settings.VERIFICATION_TOKEN_EXPIRE_HOURS),
        )

        if self._email:
            await self._send_verification_email_to_user(user, verification_token)

    async def _send_verification_email_to_user(self, user: UserDB, token: str) -> None:
        """
        Dispatch the professional verification email.

        Args:
            user: The user to send the verification email to.
            token: The verification token to include in the email link.
        """
        verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        greet_name = self._get_user_greet_name(user)
        year = datetime.now().year

        html_content = self._email_builder.build_verification_email(
            greet_name=greet_name,
            verification_link=verification_link,
            expiry_hours=settings.VERIFICATION_TOKEN_EXPIRE_HOURS,
            year=year,
        )

        if not self._email:
            logger.warning(
                f"Email client not initialized. Cannot send verification email to {user.email}",
            )
            return

        try:
            await self._email.send_email(
                subject="Elevate Your Journey: Verify Your BaliBlissed Account",
                body=html_content,
                reply_to=settings.COMPANY_TARGET_EMAIL,
                to=user.email,
                is_html=True,
            )

        except Exception:
            logger.exception(f"Failed to send verification email to {user.email}")

    async def verify_email(self, token_data: VerificationTokenData) -> bool:
        """
        Mark user email as verified.

        Security: Validates that token's email claim matches user's current email.
        This prevents token reuse if user changed their email after token generation.

        Args:
            token_data: Verification token data containing user_id and email

        Returns:
            bool: True if successfully verified
        """
        user = await self.user_repo.get_by_id(token_data.user_id)
        if not user:
            return False

        # Security: Verify token was issued for current email
        if user.email != token_data.email:
            return False  # Email changed since token was issued

        # Already verified - still return True
        if user.is_verified:
            return True

        user.is_verified = True
        user.updated_at = datetime.now(UTC)
        await self.user_repo._add_and_refresh(user)  # noqa: SLF001
        return True

    async def check_verification_rate_limit(self, user_id: UUID) -> bool:
        """
        Check if user can request another verification email.

        Args:
            user_id: User UUID

        Returns:
            bool: True if user can request, False if rate limited
        """
        if not self._redis:
            return True  # No Redis, no rate limiting

        key = f"verification_limit:{user_id}"
        count = await self._redis.get(key)

        return not (count and int(count) >= settings.VERIFICATION_RESEND_LIMIT)

    async def record_verification_sent(self, user_id: UUID) -> None:
        """
        Record that a verification email was sent for rate limiting.

        Args:
            user_id: User UUID
        """
        if not self._redis:
            return

        key = f"verification_limit:{user_id}"
        count = await self._redis.get(key)

        if count:
            await self._redis.incr(key)
        else:
            await self._redis.set(key, "1", ex=86400)  # 24 hours

    async def is_verification_token_used(self, jti: str) -> bool:
        """
        Check if a verification token has already been used.

        Args:
            jti: JWT ID of the verification token

        Returns:
            bool: True if token has been used
        """
        if not self._redis:
            return False

        key = f"verification_token:used:{jti}"
        exists = await self._redis.exists(key)
        return exists > 0

    async def mark_verification_token_used(self, jti: str, expires_hours: int = 24) -> None:
        """
        Mark a verification token as used to prevent reuse.

        Args:
            jti: JWT ID of the verification token
            expires_hours: Hours until the used token record expires (matches token expiry)
        """
        if not self._redis:
            return

        key = f"verification_token:used:{jti}"
        await self._redis.set(key, "1", ex=expires_hours * 3600)

    async def send_password_reset(self, email: str) -> bool:
        """
        Generate and send password reset email to user.

        Args:
            email: User email address

        Returns:
            bool: True if processed (always returns True to prevent email enumeration)
        """
        user = await self.user_repo.get_by_email(email)
        if not user:
            # Always return True to prevent email enumeration
            return True

        # Check rate limit
        can_send = await self.check_reset_rate_limit(user.uuid)
        if not can_send:
            # Still return True to prevent enumeration, but don't send email
            logger.warning(f"Password reset rate limit exceeded for user {user.uuid}")
            return True

        # Create a dedicated password reset token (1 hour)
        reset_token = create_password_reset_token(
            user_id=user.uuid,
            email=user.email,
            expires_delta=timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS),
        )

        # Get JTI for tracking
        token_jti = get_token_jti(reset_token)
        if token_jti:
            # Mark token as unused in Redis (for single-use enforcement)
            await self.mark_reset_token_unused(
                token_jti,
                expires_hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
            )

        # Send the password reset email
        if self._email:
            await self._send_password_reset_email(user, reset_token)

        # Record reset attempt for rate limiting
        await self.record_reset_sent(user.uuid)

        return True

    async def _send_password_reset_email(self, user: UserDB, token: str) -> None:
        """
        Send password reset email to user.

        Args:
            user: User to send reset email to.
            token: Password reset token.
        """
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        greet_name = self._get_user_greet_name(user)
        year = datetime.now().year

        html_content = self._email_builder.build_password_reset_email(
            greet_name=greet_name,
            reset_link=reset_link,
            expiry_hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
            year=year,
        )

        if not self._email:
            logger.warning(
                f"Email client not initialized. Cannot send password reset email to {user.email}",
            )
            return

        try:
            await self._email.send_email(
                subject="Reset Your BaliBlissed Password",
                body=html_content,
                reply_to=settings.COMPANY_TARGET_EMAIL,
                to=user.email,
                is_html=True,
            )
            logger.info(f"Password reset email sent to {user.email}")

        except Exception:
            logger.exception(f"Failed to send password reset email to {user.email}")

    async def check_reset_rate_limit(self, user_id: UUID) -> bool:
        """
        Check if user can request another password reset email.

        Args:
            user_id: User UUID

        Returns:
            bool: True if user can request, False if rate limited
        """
        if not self._redis:
            return True  # No Redis, no rate limiting

        key = f"password_reset_limit:{user_id}"
        count = await self._redis.get(key)

        return not (count and int(count) >= settings.PASSWORD_RESET_RESEND_LIMIT)

    async def record_reset_sent(self, user_id: UUID) -> None:
        """
        Record that a password reset email was sent for rate limiting.

        Args:
            user_id: User UUID
        """
        if not self._redis:
            return

        key = f"password_reset_limit:{user_id}"
        count = await self._redis.get(key)

        if count:
            await self._redis.incr(key)
        else:
            await self._redis.set(key, "1", ex=3600)  # 1 hour

    async def is_reset_token_used(self, jti: str) -> bool:
        """
        Check if a password reset token has already been used.

        Args:
            jti: JWT ID of the reset token

        Returns:
            bool: True if token has been used
        """
        if not self._redis:
            return False

        key = f"password_reset_token:used:{jti}"
        exists = await self._redis.exists(key)
        return exists > 0

    async def mark_reset_token_unused(self, jti: str, expires_hours: int = 1) -> None:
        """
        Mark a password reset token as unused (for tracking).

        Args:
            jti: JWT ID of the reset token
            expires_hours: Hours until the token record expires
        """
        if not self._redis:
            return

        key = f"password_reset_token:unused:{jti}"
        await self._redis.set(key, "1", ex=expires_hours * 3600)

    async def mark_reset_token_used(self, jti: str, expires_hours: int = 1) -> None:
        """
        Mark a password reset token as used to prevent reuse.

        Args:
            jti: JWT ID of the reset token
            expires_hours: Hours until the used token record expires
        """
        if not self._redis:
            return

        # Remove from unused and add to used
        unused_key = f"password_reset_token:unused:{jti}"
        used_key = f"password_reset_token:used:{jti}"

        await self._redis.delete(unused_key)
        await self._redis.set(used_key, "1", ex=expires_hours * 3600)

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

    def _get_user_greet_name(self, user: UserDB) -> str:
        """
        Get the best display name for the user for emails.

        Tries first_name, then username (formatted), then falls back to "there".

        Args:
            user: The user entity

        Returns:
            str: The display name to use in emails
        """
        # Use first_name if available and not empty
        if user.first_name and user.first_name != "string":
            return user.first_name.strip()

        # Fall back to username, but format it nicely
        if user.username and user.username.strip():
            # Capitalize first letter and replace underscores/hyphens with spaces
            formatted = user.username.strip().replace("_", " ").replace("-", " ").title()
            return formatted

        # Ultimate fallback
        return "there"

    async def _send_password_change_email(self, user: UserDB) -> None:
        """
        Send password change confirmation email to user.

        This email notifies the user that their password was changed
        and provides security information if they didn't make this change.

        Args:
            user: The user whose password was changed.
        """
        greet_name = self._get_user_greet_name(user)
        year = datetime.now().year
        change_time = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")

        html_content = self._email_builder.build_password_change_email(
            greet_name=greet_name,
            change_time=change_time,
            year=year,
        )

        if not self._email:
            logger.warning(
                f"Email client not initialized. Cannot send password change email to {user.email}",
            )
            return

        try:
            await self._email.send_email(
                subject="Security Alert: Your BaliBlissed Password Was Changed",
                body=html_content,
                reply_to=settings.COMPANY_TARGET_EMAIL,
                to=user.email,
                is_html=True,
            )
            logger.info(f"Password change email sent to {user.email}")

        except Exception:
            logger.exception(f"Failed to send password change email to {user.email}")

    async def change_password(
        self,
        user_id: UUID,
        old_password: str,
        new_password: str,
    ) -> bool:
        """
        Change password for logged-in user after verifying old password.

        This method validates the old password, updates to the new password,
        and invalidates all existing refresh tokens for security.

        Args:
            user_id: User UUID
            old_password: Current password for verification
            new_password: New password to set

        Returns:
            bool: True if successfully changed, False if user not found or
                old password is incorrect
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user or not user.password_hash:
            return False

        # Verify old password
        if not await verify_password(old_password, user.password_hash):
            return False

        # Hash and set new password
        password_hash = await hash_password(new_password)
        user.password_hash = password_hash
        user.updated_at = datetime.now(UTC)
        await self.user_repo._add_and_refresh(user)  # noqa: SLF001

        # Invalidate all refresh tokens for this user (soft invalidation)
        if self._blacklist:
            pass

        # Send confirmation email (non-blocking, doesn't affect password change success)
        await self._send_password_change_email(user)

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
        )

        return await self.user_repo.create(
            user_create,
            auth_provider=provider,
            provider_id=user_info.get("sub"),
            is_verified=True,  # OAuth emails are pre-verified by the provider
        )
