"""High-value tests for AuthService security-critical behaviors."""

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import UUID

import pytest

from app.configs.settings import settings
from app.errors.auth import (
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    TokenRevokedError,
)
from app.models import UserDB
from app.schemas.auth import Token, TokenData, VerificationTokenData
from app.services.auth import AuthService

pytestmark = pytest.mark.asyncio


def redis_mock(service: AuthService) -> MagicMock:
    redis = service._redis
    assert redis is not None
    return cast(MagicMock, redis)


def async_mock(method: object) -> AsyncMock:
    return cast(AsyncMock, method)


@pytest.fixture
def auth_service_deps(
    mock_redis_client: MagicMock,
) -> tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock]:
    mock_repo = MagicMock()
    mock_repo.get_by_email = AsyncMock()
    mock_repo.get_by_username = AsyncMock()
    mock_repo.get_by_id = AsyncMock()
    mock_repo.add_and_refresh = AsyncMock()
    mock_repo.create = AsyncMock()

    mock_blacklist = MagicMock()
    mock_blacklist.is_blacklisted = AsyncMock(return_value=False)
    mock_blacklist.add_to_blacklist = AsyncMock(return_value=True)

    mock_tracker = MagicMock()
    mock_tracker.is_locked_out = AsyncMock(return_value=(False, 0))
    mock_tracker.record_failed_attempt = AsyncMock()
    mock_tracker.reset_attempts = AsyncMock()

    # Create mock password hasher
    mock_hasher = MagicMock()
    mock_hasher.hash_password = AsyncMock(return_value="$argon2id$v=19$m=65536,t=3,p=4$hashed")
    mock_hasher.verify_password = AsyncMock(return_value=True)

    service = AuthService(
        mock_repo,
        token_blacklist=mock_blacklist,
        login_tracker=mock_tracker,
        redis_client=mock_redis_client,
        email_client=MagicMock(),
    )
    service._send_password_reset_email = AsyncMock()
    service._send_password_change_email = AsyncMock()
    service.mark_reset_token_unused = AsyncMock()
    service.record_reset_sent = AsyncMock()
    service.check_reset_rate_limit = AsyncMock(return_value=True)
    return service, mock_repo, mock_blacklist, mock_tracker, mock_hasher


async def test_authenticate_user_accepts_email_and_resets_attempts(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, _, mock_tracker, mock_hasher = auth_service_deps
    mock_repo.get_by_email.return_value = sample_user

    result = await service.authenticate_user(mock_hasher, sample_user.email, "Password123")

    assert result is sample_user
    mock_repo.get_by_email.assert_awaited_once_with(sample_user.email)
    mock_tracker.reset_attempts.assert_awaited_once_with(sample_user.email)
    mock_tracker.record_failed_attempt.assert_not_awaited()


async def test_authenticate_user_records_failed_attempt_for_bad_password(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, _, mock_tracker, mock_hasher = auth_service_deps
    mock_repo.get_by_username.return_value = sample_user
    mock_hasher.verify_password.return_value = False

    with pytest.raises(InvalidCredentialsError):
        await service.authenticate_user(mock_hasher, sample_user.username, "wrong-password")

    mock_tracker.record_failed_attempt.assert_awaited_once_with(sample_user.username)
    mock_tracker.reset_attempts.assert_not_awaited()


async def test_create_token_for_user_builds_bearer_token(sample_user: UserDB) -> None:
    service = AuthService(MagicMock())

    with (
        patch(
            "app.services.auth.create_access_token",
            return_value="access-token",
        ) as create_access,
        patch(
            "app.services.auth.create_refresh_token",
            return_value="refresh-token",
        ) as create_refresh,
    ):
        result = service.create_token_for_user(sample_user)

    assert result == Token(
        access_token="access-token",
        refresh_token="refresh-token",
        token_type="bearer",
    )
    create_access.assert_called_once()
    create_refresh.assert_called_once()


async def test_refresh_tokens_rejects_invalid_token(
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, _, _, _, _ = auth_service_deps

    with (
        patch("app.services.auth.decode_refresh_token", return_value=None),
        pytest.raises(InvalidRefreshTokenError),
    ):
        await service.refresh_tokens("invalid-refresh-token")


async def test_refresh_tokens_rejects_revoked_token(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, mock_blacklist, _, _ = auth_service_deps
    token_data = TokenData(
        username=sample_user.username,
        user_id=sample_user.uuid,
        jti="revoked-jti",
        token_type="refresh",
    )
    mock_blacklist.is_blacklisted.return_value = True

    with (
        patch("app.services.auth.decode_refresh_token", return_value=token_data),
        pytest.raises(TokenRevokedError),
    ):
        await service.refresh_tokens("revoked-refresh-token")

    mock_repo.get_by_id.assert_not_awaited()


async def test_refresh_tokens_blacklists_old_refresh_and_rotates_tokens(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, mock_blacklist, _, _ = auth_service_deps
    token_data = TokenData(
        username=sample_user.username,
        user_id=sample_user.uuid,
        jti="refresh-jti",
        token_type="refresh",
    )
    expiry = datetime.now(UTC) + timedelta(days=1)
    rotated = Token(access_token="new-access", refresh_token="new-refresh", token_type="bearer")
    mock_repo.get_by_id.return_value = sample_user
    service.create_token_for_user = MagicMock(return_value=rotated)

    with (
        patch("app.services.auth.decode_refresh_token", return_value=token_data),
        patch("app.services.auth.get_token_expiry", return_value=expiry),
    ):
        result = await service.refresh_tokens("valid-refresh-token")

    assert result is rotated
    mock_blacklist.add_to_blacklist.assert_awaited_once_with("refresh-jti", expiry)
    service.create_token_for_user.assert_called_once_with(sample_user)


async def test_logout_user_blacklists_access_and_refresh_tokens(
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, _, mock_blacklist, _, _ = auth_service_deps
    access_exp = datetime.now(UTC) + timedelta(minutes=30)
    refresh_exp = datetime.now(UTC) + timedelta(days=7)

    with (
        patch("app.services.auth.get_token_jti", side_effect=["access-jti", "refresh-jti"]),
        patch("app.services.auth.get_token_expiry", side_effect=[access_exp, refresh_exp]),
    ):
        result = await service.logout_user("access-token", "refresh-token")

    assert result is True
    assert mock_blacklist.add_to_blacklist.await_args_list == [
        call("access-jti", access_exp),
        call("refresh-jti", refresh_exp),
    ]


async def test_send_verification_email_creates_token_and_dispatches_email(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, _, _, _, _ = auth_service_deps
    service._send_verification_email_to_user = AsyncMock()

    with patch("app.services.auth.create_verification_token", return_value="verify-token"):
        await service.send_verification_email(sample_user)

    service._send_verification_email_to_user.assert_awaited_once_with(sample_user, "verify-token")


async def test_verify_email_rejects_token_for_stale_email(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, _, _, _ = auth_service_deps
    mock_repo.get_by_id.return_value = sample_user
    token_data = VerificationTokenData(
        user_id=sample_user.uuid,
        email="changed@example.com",
        jti="verify-jti",
    )

    result = await service.verify_email(token_data)

    assert result is False
    mock_repo.add_and_refresh.assert_not_awaited()


async def test_verify_email_marks_unverified_user_as_verified(
    unverified_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, _, _, _ = auth_service_deps
    mock_repo.get_by_id.return_value = unverified_user
    token_data = VerificationTokenData(
        user_id=unverified_user.uuid,
        email=unverified_user.email,
        jti="verify-jti",
    )

    result = await service.verify_email(token_data)

    assert result is True
    assert unverified_user.is_verified is True
    mock_repo.add_and_refresh.assert_awaited_once_with(unverified_user)


async def test_check_verification_rate_limit_blocks_when_limit_reached(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, _, _, _, _ = auth_service_deps
    redis = redis_mock(service)
    redis.get.return_value = str(settings.VERIFICATION_RESEND_LIMIT)

    result = await service.check_verification_rate_limit(sample_user.uuid)

    assert result is False


async def test_record_verification_sent_sets_counter_for_first_request(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, _, _, _, _ = auth_service_deps
    redis = redis_mock(service)
    redis.get.return_value = None

    await service.record_verification_sent(sample_user.uuid)

    redis.set.assert_awaited_once_with(
        f"verification_limit:{sample_user.uuid}",
        "1",
        ex=86400,
    )


async def test_verification_token_helpers_use_redis_expiry(
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, _, _, _, _ = auth_service_deps
    redis = redis_mock(service)
    redis.exists.return_value = 1

    assert await service.is_verification_token_used("verify-jti") is True

    await service.mark_verification_token_used("verify-jti", expires_hours=3)

    redis.set.assert_awaited_with("verification_token:used:verify-jti", "1", ex=10800)


async def test_send_password_reset_hides_missing_email(
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, _, _, _ = auth_service_deps
    mock_repo.get_by_email.return_value = None

    result = await service.send_password_reset("missing@example.com")

    assert result is True
    async_mock(service.mark_reset_token_unused).assert_not_awaited()
    async_mock(service.record_reset_sent).assert_not_awaited()
    async_mock(service._send_password_reset_email).assert_not_awaited()


async def test_send_password_reset_swallows_rate_limit_without_sending(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, _, _, _ = auth_service_deps
    mock_repo.get_by_email.return_value = sample_user
    service.check_reset_rate_limit.return_value = False

    result = await service.send_password_reset(sample_user.email)

    assert result is True
    async_mock(service.mark_reset_token_unused).assert_not_awaited()
    async_mock(service._send_password_reset_email).assert_not_awaited()
    async_mock(service.record_reset_sent).assert_not_awaited()


async def test_send_password_reset_tracks_single_use_token_and_records_send(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, _, _, _ = auth_service_deps
    mock_repo.get_by_email.return_value = sample_user

    with (
        patch("app.services.auth.create_password_reset_token", return_value="reset-token"),
        patch("app.services.auth.get_token_jti", return_value="reset-jti"),
    ):
        result = await service.send_password_reset(sample_user.email)

    assert result is True
    async_mock(service.mark_reset_token_unused).assert_awaited_once_with(
        "reset-jti",
        expires_hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
    )
    async_mock(service._send_password_reset_email).assert_awaited_once_with(
        sample_user,
        "reset-token",
    )
    async_mock(service.record_reset_sent).assert_awaited_once_with(sample_user.uuid)


async def test_reset_helpers_use_redis_for_rate_limits_and_single_use_tokens(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, _, _, _, _ = auth_service_deps
    redis = redis_mock(service)
    helper_service = AuthService(MagicMock(), redis_client=redis)
    helper_redis = redis_mock(helper_service)
    helper_redis.get.side_effect = [str(settings.PASSWORD_RESET_RESEND_LIMIT), None]
    helper_redis.exists.return_value = 1

    assert await helper_service.check_reset_rate_limit(sample_user.uuid) is False

    await helper_service.record_reset_sent(sample_user.uuid)
    assert await helper_service.is_reset_token_used("reset-jti") is True
    await helper_service.mark_reset_token_used("reset-jti", expires_hours=2)

    helper_redis.set.assert_any_await(
        f"password_reset_limit:{sample_user.uuid}",
        "1",
        ex=3600,
    )
    helper_redis.delete.assert_awaited_once_with("password_reset_token:unused:reset-jti")
    helper_redis.set.assert_any_await("password_reset_token:used:reset-jti", "1", ex=7200)


async def test_reset_password_hashes_and_persists_user(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, _, _, mock_hasher = auth_service_deps
    mock_repo.get_by_id.return_value = sample_user

    result = await service.reset_password(mock_hasher, sample_user.uuid, "NewPassword123")

    assert result is True
    assert sample_user.password_hash == "$argon2id$v=19$m=65536,t=3,p=4$hashed"
    mock_hasher.hash_password.assert_awaited_once_with("NewPassword123")
    mock_repo.add_and_refresh.assert_awaited_once_with(sample_user)


async def test_change_password_returns_false_for_wrong_current_password(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, _, _, mock_hasher = auth_service_deps
    mock_repo.get_by_id.return_value = sample_user
    mock_hasher.verify_password.return_value = False

    result = await service.change_password(
        mock_hasher,
        sample_user.uuid,
        "wrong-old",
        "NewPassword123",
    )

    assert result is False
    mock_repo.add_and_refresh.assert_not_awaited()
    async_mock(service._send_password_change_email).assert_not_awaited()


async def test_change_password_updates_hash_and_sends_confirmation(
    sample_user: UserDB,
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, _, _, mock_hasher = auth_service_deps
    mock_repo.get_by_id.return_value = sample_user
    # Save original password_hash before change_password modifies it
    original_password_hash = sample_user.password_hash

    result = await service.change_password(
        mock_hasher,
        sample_user.uuid,
        "OldPassword123",
        "NewPassword123",
    )

    assert result is True
    assert sample_user.password_hash == "$argon2id$v=19$m=65536,t=3,p=4$hashed"
    mock_hasher.verify_password.assert_awaited_once_with(
        "OldPassword123",
        original_password_hash,  # Original password hash from fixture
    )
    mock_hasher.hash_password.assert_awaited_once_with("NewPassword123")
    mock_repo.add_and_refresh.assert_awaited_once_with(sample_user)
    async_mock(service._send_password_change_email).assert_awaited_once_with(sample_user)


async def test_get_or_create_oauth_user_requires_email(
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, _, _, _, mock_hasher = auth_service_deps

    with pytest.raises(ValueError, match="Email required from identity provider"):
        await service.get_or_create_oauth_user(mock_hasher, {}, "google")


async def test_get_or_create_oauth_user_marks_existing_user_verified(
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, _, _, mock_hasher = auth_service_deps
    existing_user = UserDB(
        uuid=UUID("12345678-1234-5678-1234-567812345679"),
        username="oauth_user",
        email="oauth@example.com",
        is_verified=False,
    )
    mock_repo.get_by_email.return_value = existing_user

    result = await service.get_or_create_oauth_user(
        mock_hasher,
        {"email": existing_user.email},
        "google",
    )

    assert result is existing_user
    assert existing_user.is_verified is True
    mock_repo.add_and_refresh.assert_awaited_once_with(existing_user)
    mock_repo.create.assert_not_awaited()


async def test_get_or_create_oauth_user_creates_new_verified_user(
    auth_service_deps: tuple[AuthService, MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    service, mock_repo, _, _, mock_hasher = auth_service_deps
    created_user = UserDB(
        uuid=UUID("12345678-1234-5678-1234-567812345680"),
        username="oauthuser_1234",
        email="oauthuser@example.com",
        is_verified=True,
    )
    mock_repo.get_by_email.return_value = None
    mock_repo.create.return_value = created_user
    user_info = {
        "email": "oauthuser@example.com",
        "given_name": "OAuth",
        "family_name": "User",
        "picture": "https://example.com/avatar.jpg",
        "sub": "provider-sub",
    }

    with patch(
        "app.services.auth.uuid4",
        return_value=UUID("12345678-1234-5678-1234-567812345678"),
    ):
        result = await service.get_or_create_oauth_user(
            mock_hasher,
            user_info,
            "google",
            timezone="Asia/Makassar",
        )

    assert result is created_user
    args = mock_repo.create.await_args.args
    user_create_schema, create_update = args[0], args[1]
    # Now user_create is a UserCreate dataclass
    assert user_create_schema.username == "oauthuser_1234"
    assert user_create_schema.email == "oauthuser@example.com"
    assert user_create_schema.first_name == "OAuth"
    assert user_create_schema.last_name == "User"
    assert str(user_create_schema.profile_picture) == "https://example.com/avatar.jpg"
    # The other params are fields of CreateUpdate dataclass
    assert create_update.auth_provider == "google"
    assert create_update.provider_id == "provider-sub"
    assert create_update.is_verified is True
    assert create_update.timezone == "Asia/Makassar"
