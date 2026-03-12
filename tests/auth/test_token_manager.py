"""Tests for the enhanced JWT token manager."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jose import jwt

from app.configs.settings import settings
from app.managers.token_manager import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    create_verification_token,
    decode_access_token,
    decode_password_reset_token,
    decode_refresh_token,
    decode_verification_token,
    get_token_expiry,
    get_token_jti,
)


def _encode_custom_token(claims: dict[str, object]) -> str:
    """Create a JWT with project settings for negative-path tests."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid4()),
        "user_id": str(uuid4()),
        "jti": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        **claims,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


class TestCreateAccessToken:
    """Test cases for create_access_token function."""

    def test_creates_valid_token(self) -> None:
        """Test that access token is created successfully."""
        user_id = uuid4()
        username = "testuser"

        token = create_access_token(user_id=user_id, username=username)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_correct_claims(self) -> None:
        """Test that access token contains all required claims."""
        user_id = uuid4()
        username = "testuser"

        token = create_access_token(user_id=user_id, username=username)
        token_data = decode_access_token(token)

        assert token_data is not None
        assert token_data.username == username
        assert token_data.user_id == user_id
        assert token_data.token_type == "access"
        assert token_data.jti is not None

    def test_custom_expiration(self) -> None:
        """Test that custom expiration is respected."""
        user_id = uuid4()
        username = "testuser"
        expires_delta = timedelta(hours=2)

        token = create_access_token(
            user_id=user_id,
            username=username,
            expires_delta=expires_delta,
        )

        assert token is not None
        expiry = get_token_expiry(token)
        assert expiry is not None


class TestCreateRefreshToken:
    """Test cases for create_refresh_token function."""

    def test_creates_valid_token(self) -> None:
        """Test that refresh token is created successfully."""
        user_id = uuid4()
        username = "testuser"

        token = create_refresh_token(user_id=user_id, username=username)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_correct_claims(self) -> None:
        """Test that refresh token contains all required claims."""
        user_id = uuid4()
        username = "testuser"

        token = create_refresh_token(user_id=user_id, username=username)
        token_data = decode_refresh_token(token)

        assert token_data is not None
        assert token_data.username == username
        assert token_data.user_id == user_id
        assert token_data.token_type == "refresh"
        assert token_data.jti is not None

    def test_refresh_token_different_from_access(self) -> None:
        """Test that refresh token is different from access token."""
        user_id = uuid4()
        username = "testuser"

        access_token = create_access_token(user_id=user_id, username=username)
        refresh_token = create_refresh_token(user_id=user_id, username=username)

        assert access_token != refresh_token


class TestDecodeAccessToken:
    """Test cases for decode_access_token function."""

    def test_decodes_valid_token(self) -> None:
        """Test that valid access token is decoded correctly."""
        user_id = uuid4()
        username = "testuser"
        token = create_access_token(user_id=user_id, username=username)

        token_data = decode_access_token(token)

        assert token_data is not None
        assert token_data.username == username
        assert token_data.user_id == user_id

    def test_rejects_invalid_token(self) -> None:
        """Test that invalid token returns None."""
        result = decode_access_token("invalid.token.here")

        assert result is None

    def test_rejects_refresh_token(self) -> None:
        """Test that refresh token is rejected when decoding as access token."""
        user_id = uuid4()
        username = "testuser"
        refresh_token = create_refresh_token(user_id=user_id, username=username)

        result = decode_access_token(refresh_token)

        assert result is None

    def test_rejects_expired_token(self) -> None:
        """Test that expired token returns None."""
        user_id = uuid4()
        username = "testuser"
        token = create_access_token(
            user_id=user_id,
            username=username,
            expires_delta=timedelta(seconds=-1),
        )

        result = decode_access_token(token)

        assert result is None


class TestDecodeRefreshToken:
    """Test cases for decode_refresh_token function."""

    def test_decodes_valid_token(self) -> None:
        """Test that valid refresh token is decoded correctly."""
        user_id = uuid4()
        username = "testuser"
        token = create_refresh_token(user_id=user_id, username=username)

        token_data = decode_refresh_token(token)

        assert token_data is not None
        assert token_data.username == username
        assert token_data.user_id == user_id

    def test_rejects_access_token(self) -> None:
        """Test that access token is rejected when decoding as refresh token."""
        user_id = uuid4()
        username = "testuser"
        access_token = create_access_token(user_id=user_id, username=username)

        result = decode_refresh_token(access_token)

        assert result is None


class TestVerificationTokens:
    """Test cases for email verification tokens."""

    def test_verification_token_round_trip(self) -> None:
        """Verification tokens should round-trip with bound email and JTI."""
        user_id = uuid4()
        email = "verify@example.com"

        token = create_verification_token(user_id=user_id, email=email)
        token_data = decode_verification_token(token)

        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.email == email
        assert token_data.jti is not None

    def test_verification_token_rejects_wrong_token_type(self) -> None:
        """Verification decoder should reject regular access tokens."""
        user_id = uuid4()
        access_token = create_access_token(user_id=user_id, username="testuser")

        assert decode_verification_token(access_token) is None

    def test_verification_token_rejects_missing_email_claim(self) -> None:
        """Verification decoder should reject tokens without the bound email claim."""
        token = _encode_custom_token({"type": "verification", "email": None})

        assert decode_verification_token(token) is None


class TestPasswordResetTokens:
    """Test cases for password reset tokens."""

    def test_password_reset_token_round_trip(self) -> None:
        """Password reset tokens should preserve user, email, and JTI."""
        user_id = uuid4()
        email = "reset@example.com"

        token = create_password_reset_token(user_id=user_id, email=email)
        token_data = decode_password_reset_token(token)

        assert token_data is not None
        assert token_data.user_id == user_id
        assert token_data.email == email
        assert token_data.jti is not None

    def test_password_reset_token_rejects_wrong_token_type(self) -> None:
        """Password reset decoder should reject verification tokens."""
        user_id = uuid4()
        token = create_verification_token(user_id=user_id, email="verify@example.com")

        assert decode_password_reset_token(token) is None

    def test_password_reset_token_rejects_missing_email_claim(self) -> None:
        """Password reset decoder should reject tokens without email binding."""
        token = _encode_custom_token({"type": "password_reset", "email": None})

        assert decode_password_reset_token(token) is None


class TestGetTokenExpiry:
    """Test cases for get_token_expiry function."""

    def test_gets_expiry_from_valid_token(self) -> None:
        """Test that expiry is extracted from valid token."""
        user_id = uuid4()
        username = "testuser"
        token = create_access_token(user_id=user_id, username=username)

        expiry = get_token_expiry(token)

        assert expiry is not None

    def test_returns_none_for_invalid_token(self) -> None:
        """Test that None is returned for invalid token."""
        result = get_token_expiry("invalid.token.here")

        assert result is None


class TestGetTokenJti:
    """Test cases for get_token_jti function."""

    def test_gets_jti_from_valid_token(self) -> None:
        """Test that JTI is extracted from valid token."""
        user_id = uuid4()
        username = "testuser"
        token = create_access_token(user_id=user_id, username=username)

        jti = get_token_jti(token)

        assert jti is not None
        assert isinstance(jti, str)

    def test_returns_none_for_invalid_token(self) -> None:
        """Test that None is returned for invalid token."""
        result = get_token_jti("invalid.token.here")

        assert result is None

    def test_each_token_has_unique_jti(self) -> None:
        """Test that each token has a unique JTI."""
        user_id = uuid4()
        username = "testuser"

        token1 = create_access_token(user_id=user_id, username=username)
        token2 = create_access_token(user_id=user_id, username=username)

        jti1 = get_token_jti(token1)
        jti2 = get_token_jti(token2)

        assert jti1 != jti2
