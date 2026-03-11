"""High-value route tests for core auth endpoints."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.configs.settings import settings
from app.dependencies.dependencies import (
    get_auth_service,
    get_current_user,
    get_current_user_response,
    get_user_repository,
)
from app.errors.auth import InvalidCredentialsError
from app.main import app
from app.models import UserDB
from app.schemas.auth import PasswordResetTokenData, VerificationTokenData
from app.schemas.user import validate_user_response

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def cleanup_app_overrides() -> Generator[None]:
    """Clear dependency overrides between tests."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_route_deps() -> tuple[MagicMock, MagicMock]:
    """Provide mocked auth service and user repository for route tests."""
    mock_repo = MagicMock()
    mock_repo.get_by_email = AsyncMock(return_value=None)
    mock_repo.get_by_id = AsyncMock(return_value=None)

    mock_auth_service = MagicMock()
    mock_auth_service.user_repo = mock_repo
    mock_auth_service.authenticate_user = AsyncMock()
    mock_auth_service.refresh_tokens = AsyncMock()
    mock_auth_service.logout_user = AsyncMock(return_value=True)
    mock_auth_service.is_verification_token_used = AsyncMock(return_value=False)
    mock_auth_service.verify_email = AsyncMock(return_value=True)
    mock_auth_service.mark_verification_token_used = AsyncMock()
    mock_auth_service.check_verification_rate_limit = AsyncMock(return_value=True)
    mock_auth_service.send_verification_email = AsyncMock()
    mock_auth_service.record_verification_sent = AsyncMock()
    mock_auth_service.send_password_reset = AsyncMock(return_value=True)
    mock_auth_service.is_reset_token_used = AsyncMock(return_value=False)
    mock_auth_service.reset_password = AsyncMock(return_value=True)
    mock_auth_service.mark_reset_token_used = AsyncMock()
    mock_auth_service.change_password = AsyncMock(return_value=True)
    mock_auth_service.create_token_for_user = MagicMock(
        return_value={
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "token_type": "bearer",
        },
    )

    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service
    app.dependency_overrides[get_user_repository] = lambda: mock_repo
    return mock_auth_service, mock_repo


async def test_login_for_access_token_returns_token_pair(
    client: AsyncClient,
    sample_user: UserDB,
    auth_route_deps: tuple[MagicMock, MagicMock],
) -> None:
    mock_auth_service, _ = auth_route_deps
    mock_auth_service.authenticate_user.return_value = sample_user

    response = await client.post(
        "/auth/login",
        data={"username": sample_user.username, "password": "Password123"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "new-access-token"
    mock_auth_service.authenticate_user.assert_awaited_once_with(
        sample_user.username,
        "Password123",
    )
    mock_auth_service.create_token_for_user.assert_called_once_with(sample_user)


async def test_login_for_access_token_returns_401_for_invalid_credentials(
    client: AsyncClient,
    auth_route_deps: tuple[MagicMock, MagicMock],
) -> None:
    mock_auth_service, _ = auth_route_deps
    mock_auth_service.authenticate_user.side_effect = InvalidCredentialsError()

    response = await client.post(
        "/auth/login",
        data={"username": "missing@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert "doesn't match our records" in response.json()["detail"]
    mock_auth_service.create_token_for_user.assert_not_called()


async def test_refresh_token_returns_rotated_tokens(
    client: AsyncClient,
    auth_route_deps: tuple[MagicMock, MagicMock],
) -> None:
    mock_auth_service, _ = auth_route_deps
    mock_auth_service.refresh_tokens.return_value = {
        "access_token": "rotated-access",
        "refresh_token": "rotated-refresh",
        "token_type": "bearer",
    }

    response = await client.post("/auth/refresh", json={"refresh_token": "old-refresh"})

    assert response.status_code == 200
    assert response.json()["refresh_token"] == "rotated-refresh"
    mock_auth_service.refresh_tokens.assert_awaited_once_with("old-refresh")


async def test_logout_blacklists_tokens_and_returns_success(
    client: AsyncClient,
    auth_route_deps: tuple[MagicMock, MagicMock],
) -> None:
    mock_auth_service, _ = auth_route_deps

    response = await client.post(
        "/auth/logout",
        json={"refresh_token": "refresh-token"},
        headers={"Authorization": "Bearer access-token"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Successfully logged out"
    mock_auth_service.logout_user.assert_awaited_once_with("access-token", "refresh-token")


async def test_verify_email_returns_used_token_error_without_verifying(
    client: AsyncClient,
    sample_user: UserDB,
    auth_route_deps: tuple[MagicMock, MagicMock],
) -> None:
    mock_auth_service, _ = auth_route_deps
    token_data = VerificationTokenData(
        user_id=sample_user.uuid,
        email=sample_user.email,
        jti="used-jti",
    )
    mock_auth_service.is_verification_token_used.return_value = True

    with patch("app.routes.auth.decode_verification_token", return_value=token_data):
        response = await client.post("/auth/verify-email", json={"token": "verification-token"})

    assert response.status_code == 401
    assert "already been used" in response.json()["detail"]
    mock_auth_service.verify_email.assert_not_awaited()
    mock_auth_service.mark_verification_token_used.assert_not_awaited()


async def test_verify_email_marks_token_used_on_success(
    client: AsyncClient,
    sample_user: UserDB,
    auth_route_deps: tuple[MagicMock, MagicMock],
) -> None:
    mock_auth_service, _ = auth_route_deps
    token_data = VerificationTokenData(
        user_id=sample_user.uuid,
        email=sample_user.email,
        jti="verify-jti",
    )

    with patch("app.routes.auth.decode_verification_token", return_value=token_data):
        response = await client.post("/auth/verify-email", json={"token": "verification-token"})

    assert response.status_code == 200
    assert response.json()["message"] == "Email verified successfully"
    mock_auth_service.verify_email.assert_awaited_once_with(token_data)
    mock_auth_service.mark_verification_token_used.assert_awaited_once_with(
        "verify-jti",
        expires_hours=settings.VERIFICATION_TOKEN_EXPIRE_HOURS,
    )


async def test_resend_verification_hides_unknown_email_state(
    client: AsyncClient,
    auth_route_deps: tuple[MagicMock, MagicMock],
) -> None:
    mock_auth_service, mock_repo = auth_route_deps
    mock_repo.get_by_email.return_value = None

    response = await client.post(
        "/auth/resend-verification",
        json={"email": "unknown@example.com"},
    )

    assert response.status_code == 200
    assert "registered and unverified" in response.json()["message"]
    mock_auth_service.check_verification_rate_limit.assert_not_awaited()
    mock_auth_service.send_verification_email.assert_not_awaited()


async def test_resend_verification_returns_429_when_user_is_rate_limited(
    client: AsyncClient,
    unverified_user: UserDB,
    auth_route_deps: tuple[MagicMock, MagicMock],
) -> None:
    mock_auth_service, mock_repo = auth_route_deps
    mock_repo.get_by_email.return_value = unverified_user
    mock_auth_service.check_verification_rate_limit.return_value = False

    response = await client.post(
        "/auth/resend-verification",
        json={"email": unverified_user.email},
    )

    assert response.status_code == 429
    assert "Too many verification email requests" in response.json()["detail"]
    mock_auth_service.send_verification_email.assert_not_awaited()


async def test_forgot_password_always_returns_generic_success(
    client: AsyncClient,
    auth_route_deps: tuple[MagicMock, MagicMock],
) -> None:
    mock_auth_service, _ = auth_route_deps

    response = await client.post("/auth/forgot-password", json={"email": "missing@example.com"})

    assert response.status_code == 200
    assert response.json()["message"] == "If the email exists, a reset link has been sent"
    mock_auth_service.send_password_reset.assert_awaited_once_with("missing@example.com")


async def test_reset_password_returns_used_token_error(
    client: AsyncClient,
    sample_user: UserDB,
    auth_route_deps: tuple[MagicMock, MagicMock],
) -> None:
    mock_auth_service, _ = auth_route_deps
    token_data = PasswordResetTokenData(
        user_id=sample_user.uuid,
        email=sample_user.email,
        jti="reset-jti",
    )
    mock_auth_service.is_reset_token_used.return_value = True

    with patch("app.routes.auth.decode_password_reset_token", return_value=token_data):
        response = await client.post(
            "/auth/reset-password",
            json={"token": "reset-token", "new_password": "NewPassword123"},
        )

    assert response.status_code == 401
    assert "already been used" in response.json()["detail"]
    mock_auth_service.reset_password.assert_not_awaited()


async def test_reset_password_marks_token_used_after_success(
    client: AsyncClient,
    sample_user: UserDB,
    auth_route_deps: tuple[MagicMock, MagicMock],
) -> None:
    mock_auth_service, mock_repo = auth_route_deps
    token_data = PasswordResetTokenData(
        user_id=sample_user.uuid,
        email=sample_user.email,
        jti="reset-jti",
    )
    mock_repo.get_by_id.return_value = sample_user

    with patch("app.routes.auth.decode_password_reset_token", return_value=token_data):
        response = await client.post(
            "/auth/reset-password",
            json={"token": "reset-token", "new_password": "NewPassword123"},
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Password reset successfully"
    mock_auth_service.reset_password.assert_awaited_once_with(sample_user.uuid, "NewPassword123")
    mock_auth_service.mark_reset_token_used.assert_awaited_once_with(
        "reset-jti",
        expires_hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
    )


async def test_change_password_returns_bad_request_when_service_rejects_change(
    client: AsyncClient,
    sample_user: UserDB,
    auth_route_deps: tuple[MagicMock, MagicMock],
) -> None:
    mock_auth_service, _ = auth_route_deps
    mock_auth_service.change_password.return_value = False
    app.dependency_overrides[get_current_user] = lambda: sample_user

    response = await client.post(
        "/auth/change-password",
        json={
            "old_password": "OldPassword123",
            "new_password": "NewPassword123",
            "confirm_new_password": "NewPassword123",
        },
    )

    assert response.status_code == 400
    assert "couldn't change your password" in response.json()["detail"].lower()
    mock_auth_service.change_password.assert_awaited_once_with(
        user_id=sample_user.uuid,
        old_password="OldPassword123",
        new_password="NewPassword123",
    )


async def test_read_users_me_returns_authenticated_user_profile(
    client: AsyncClient,
    sample_user: UserDB,
) -> None:

    app.dependency_overrides[get_current_user_response] = lambda: validate_user_response(
        sample_user,
    )

    response = await client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["id"] == str(sample_user.uuid)
    assert response.json()["username"] == sample_user.username
    assert response.json()["email"] == sample_user.email
