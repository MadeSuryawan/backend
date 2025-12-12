"""Authentication service handling manual and OAuth flows."""

from datetime import timedelta
from typing import Any
from uuid import uuid4

from app.errors.auth import InvalidCredentialsError
from app.managers.password_manager import verify_password
from app.managers.token_manager import create_access_token
from app.models import UserDB
from app.repositories import UserRepository
from app.schemas.auth import Token
from app.schemas.user import UserCreate


class AuthService:
    """Service for handling user authentication."""

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def authenticate_user(self, username_or_email: str, password: str | None) -> UserDB:
        """
        Authenticate a user by username or email and password.

        Args:
            username_or_email: User username or email
            password: User password

        Returns:
            UserDB: Authenticated user

        Raises:
            InvalidCredentialsError: If authentication fails
        """
        if "@" in username_or_email:
            user = await self.user_repo.get_by_email(username_or_email)
        else:
            user = await self.user_repo.get_by_username(username_or_email)

        if not user:
            raise InvalidCredentialsError

        # If user has no password (OAuth only) or password doesn't match
        if not user.password_hash or not password:
            # If user is OAuth only, they can't login with password unless they set one.
            # If password is provided but user has no hash -> Fail
            raise InvalidCredentialsError

        if not await verify_password(password, user.password_hash):
            raise InvalidCredentialsError

        return user

    def create_token_for_user(self, user: UserDB) -> Token:
        """
        Create an access token for a user.

        Args:
            user: User entity

        Returns:
            Token: Access token object
        """
        access_token_expires = timedelta(minutes=30)  # defined in settings usually, but ok here
        access_token = create_access_token(
            data={"sub": user.username},
            expires_delta=access_token_expires,
        )
        return Token(access_token=access_token, token_type="bearer")

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
            # Fallback/Error handling
            msg = "Email required from identity provider"
            raise ValueError(msg)

        existing_user = await self.user_repo.get_by_email(email)
        if existing_user:
            # Optional: Update provider info if needed
            return existing_user

        # Create new user
        # Map fields. Note: Username generation strategy needed.
        base_username = email.split("@")[0]
        # Ideally check if username exists and append random but for now simple:
        # Collision risk handled by repo (will raise error)
        # Better: use uuid or append random chars if collision (handled in loop or separate logic)
        # For this MVP, we try base, if fail, we might need retry logic or append random.

        # Simplified username generation:
        random_suffix = str(uuid4())[:4]
        final_username = f"{base_username}_{random_suffix}"

        user_create = UserCreate(
            userName=final_username,
            email=email,
            password=None,  # No password
            firstName=user_info.get("given_name"),
            lastName=user_info.get("family_name"),
            profilePicture=user_info.get("picture"),
            isVerified=True,  # OAuth emails are usually verified
        )

        # We need to manually inject auth_provider since UserCreate doesn't have it (it's in DB model)
        # But UserCreate is schema. user_repo.create takes UserCreate.
        # UserRepo.create logic:
        # db_user = UserDB(..., **schema.dict())
        # We modified UserDB to have auth_provider.
        # We need to modify UserRepo.create to accept kwargs override or handle it.
        # UserRepo.create signature: create(schema, **kwargs).

        return await self.user_repo.create(
            user_create,
            auth_provider=provider,
            provider_id=user_info.get("sub"),
        )
