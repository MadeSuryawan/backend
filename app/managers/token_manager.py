"""Token manager for handling JWT tokens with enhanced security claims."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from jose import JWTError, jwt

from app.configs import settings
from app.schemas.auth import (
    PasswordResetTokenData,
    TokenData,
    VerificationTokenData,
)


def create_access_token(
    user_id: UUID,
    username: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a new access token with enhanced security claims.

    Args:
        user_id: User's UUID
        username: User's username
        expires_delta: Optional expiration time delta

    Returns:
        str: Encoded JWT access token
    """
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": username,
        "user_id": str(user_id),
        "jti": str(uuid4()),
        "iat": now,
        "exp": expire,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "type": "access",
    }

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    user_id: UUID,
    username: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a new refresh token with enhanced security claims.

    Args:
        user_id: User's UUID
        username: User's username
        expires_delta: Optional expiration time delta

    Returns:
        str: Encoded JWT refresh token
    """
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode = {
        "sub": username,
        "user_id": str(user_id),
        "jti": str(uuid4()),
        "iat": now,
        "exp": expire,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "type": "refresh",
    }

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _decode_token(token: str, expected_type: str) -> TokenData | None:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string
        expected_type: Expected token type ('access' or 'refresh')

    Returns:
        TokenData | None: Decoded token data or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )

        username: str | None = payload.get("sub")
        user_id: str | None = payload.get("user_id")
        jti: str | None = payload.get("jti")
        token_type: str | None = payload.get("type")

        if not username or not user_id or not jti or not token_type:
            return None

        if token_type != expected_type:
            return None

        return TokenData(
            username=username,
            user_id=UUID(user_id),
            jti=jti,
            token_type=token_type,
        )
    except JWTError:
        return None


def decode_access_token(token: str) -> TokenData | None:
    """
    Decode and validate an access token.

    Args:
        token: JWT token string

    Returns:
        TokenData | None: Decoded token data or None if invalid
    """
    return _decode_token(token, "access")


def decode_refresh_token(token: str) -> TokenData | None:
    """
    Decode and validate a refresh token.

    Args:
        token: JWT token string

    Returns:
        TokenData | None: Decoded token data or None if invalid
    """
    return _decode_token(token, "refresh")


def get_token_expiry(token: str) -> datetime | None:
    """
    Extract expiration time from a token without full validation.

    Args:
        token: JWT token string

    Returns:
        datetime | None: Token expiration time or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False, "verify_iss": False},
        )
        exp = payload.get("exp")
        if exp:
            return datetime.fromtimestamp(exp, tz=UTC)
        return None
    except JWTError:
        return None


def get_token_jti(token: str) -> str | None:
    """
    Extract JTI (JWT ID) from a token without full validation.

    Args:
        token: JWT token string

    Returns:
        str | None: Token JTI or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False, "verify_iss": False},
        )
        return payload.get("jti")
    except JWTError:
        return None


def create_verification_token(
    user_id: UUID,
    email: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create email verification token with email claim binding.

    The token includes the email claim to ensure verification tokens
    cannot be reused if the user changes their email address.

    Args:
        user_id: User's UUID
        email: User's email address (bound to token)
        expires_delta: Optional expiration time delta (default: 24 hours)

    Returns:
        str: Encoded JWT verification token
    """
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(hours=settings.VERIFICATION_TOKEN_EXPIRE_HOURS))

    to_encode = {
        "sub": str(user_id),
        "user_id": str(user_id),
        "email": email,
        "jti": str(uuid4()),
        "iat": now,
        "exp": expire,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "type": "verification",
    }

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_verification_token(token: str) -> VerificationTokenData | None:
    """
    Decode and validate email verification token.

    Args:
        token: JWT token string

    Returns:
        VerificationTokenData | None: Decoded token data or None if invalid
    """

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )

        token_type: str | None = payload.get("type")
        user_id: str | None = payload.get("user_id")
        email: str | None = payload.get("email")
        jti: str | None = payload.get("jti")

        if token_type != "verification" or not user_id or not email:
            return None

        return VerificationTokenData(
            user_id=UUID(user_id),
            email=email,
            jti=jti,
        )
    except JWTError:
        return None


def create_password_reset_token(
    user_id: UUID,
    email: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create password reset token with email claim binding.

    The token includes the email claim to ensure reset tokens
    cannot be reused if the user changes their email address.

    Args:
        user_id: User's UUID
        email: User's email address (bound to token)
        expires_delta: Optional expiration time delta (default: 1 hour)

    Returns:
        str: Encoded JWT password reset token
    """
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS))

    to_encode = {
        "sub": str(user_id),
        "user_id": str(user_id),
        "email": email,
        "jti": str(uuid4()),
        "iat": now,
        "exp": expire,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "type": "password_reset",
    }

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_password_reset_token(token: str) -> PasswordResetTokenData | None:
    """
    Decode and validate password reset token.

    Args:
        token: JWT token string

    Returns:
        PasswordResetTokenData | None: Decoded token data or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )

        token_type: str | None = payload.get("type")
        user_id: str | None = payload.get("user_id")
        email: str | None = payload.get("email")
        jti: str | None = payload.get("jti")

        if token_type != "password_reset" or not user_id or not email:
            return None

        return PasswordResetTokenData(
            user_id=UUID(user_id),
            email=email,
            jti=jti,
        )
    except JWTError:
        return None
