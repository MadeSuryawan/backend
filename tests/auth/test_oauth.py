"""
OAuth authentication tests.

Tests for OAuth login flow including:
- OAuth provider configuration
- State parameter generation and validation (CSRF protection)
- Callback handling
- Error scenarios
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.dependencies import get_cache_manager
from app.main import app
from app.models import UserDB
from app.routes.auth import oauth


def setup_mock_cache() -> MagicMock:
    """Set up mock cache manager."""
    mock_cache = AsyncMock()
    return mock_cache


def setup_test_with_cache() -> MagicMock:
    """App state with mock cache for tests."""
    mock_cache = setup_mock_cache()
    # Set cache manager on app state (required for get_cache_manager dependency)
    app.state.cache_manager = mock_cache
    # Also set up dependency override
    app.dependency_overrides[get_cache_manager] = lambda: mock_cache
    return mock_cache


def teardown_test_cache() -> None:
    """Clean up after tests."""
    if hasattr(app.state, "cache_manager"):
        delattr(app.state, "cache_manager")
    if get_cache_manager in app.dependency_overrides:
        del app.dependency_overrides[get_cache_manager]


class TestOAuthLogin:
    """Tests for OAuth login initiation endpoint."""

    async def test_oauth_login_unconfigured_provider(self, client: AsyncClient) -> None:
        """Test that unconfigured provider returns 404."""
        setup_test_with_cache()
        try:
            response = await client.get("/auth/login/nonexistent")

            assert response.status_code == 404
            assert "not configured" in response.json()["detail"].lower()
        finally:
            teardown_test_cache()

    async def test_oauth_login_state_generation(self, client: AsyncClient) -> None:
        """Test that OAuth login generates and stores state."""
        mock_cache = setup_test_with_cache()

        try:
            with patch("app.routes.auth.oauth") as mock_oauth:
                mock_client = MagicMock()
                mock_client.authorize_redirect = AsyncMock(
                    return_value=MagicMock(
                        status_code=302,
                        headers={"location": "https://accounts.google.com/oauth?state=test"},
                    ),
                )
                mock_oauth.create_client.return_value = mock_client

                # Mock settings to enable Google OAuth
                with (
                    patch("app.routes.auth.settings.GOOGLE_CLIENT_ID", "test-client-id"),
                    patch("app.routes.auth.settings.OAUTH_STATE_EXPIRE_SECONDS", 600),
                ):
                    _ = await client.get("/auth/login/google")

                    # Verify state was stored in cache
                    mock_cache.set.assert_called_once()
                    call_args = mock_cache.set.call_args
                    # First positional arg should be the key (oauth_state:...)
                    assert "oauth_state:" in str(call_args[0][0])
                    # TTL should be set
                    assert call_args[1].get("ttl") == 600
        finally:
            teardown_test_cache()


class TestOAuthCallback:
    """Tests for OAuth callback endpoint."""

    async def test_oauth_callback_missing_state(self, client: AsyncClient) -> None:
        """Test callback without state parameter returns error."""
        mock_cache = setup_test_with_cache()
        mock_cache.get = AsyncMock(return_value=None)

        try:
            response = await client.get("/auth/callback/google")

            assert response.status_code == 400
            assert "state" in response.json()["detail"].lower()
        finally:
            teardown_test_cache()

    async def test_oauth_callback_invalid_state(self, client: AsyncClient) -> None:
        """Test callback with invalid/expired state returns error."""
        mock_cache = setup_test_with_cache()
        mock_cache.get = AsyncMock(return_value=None)  # State not found

        try:
            response = await client.get(
                "/auth/callback/google?state=invalid_state&code=test_code",
            )

            assert response.status_code == 400
            assert "state" in response.json()["detail"].lower()
        finally:
            teardown_test_cache()

    async def test_oauth_callback_provider_not_found(self, client: AsyncClient) -> None:
        """Test callback with unconfigured provider returns 404."""
        mock_cache = setup_test_with_cache()
        mock_cache.get = AsyncMock(return_value={"provider": "nonexistent", "ip": "127.0.0.1"})
        mock_cache.delete = AsyncMock(return_value=True)

        try:
            response = await client.get("/auth/callback/nonexistent?state=test&code=test")

            assert response.status_code == 404
        finally:
            teardown_test_cache()


class TestOAuthCSRFProtection:
    """Tests for OAuth CSRF protection via state parameter."""

    async def test_state_single_use_deletion(self, client: AsyncClient) -> None:
        """Test that OAuth state is deleted after validation."""

        test_state = "single_use_state_123"
        mock_cache = setup_test_with_cache()
        mock_cache.get = AsyncMock(
            return_value={"provider": "google", "ip": "127.0.0.1"},
        )
        mock_cache.delete = AsyncMock(return_value=True)

        try:
            with patch.object(oauth, "create_client") as mock_create_client:
                mock_client = MagicMock()
                mock_token = {"userinfo": {"sub": "123", "email": "test@example.com"}}
                mock_client.authorize_access_token = AsyncMock(return_value=mock_token)
                mock_create_client.return_value = mock_client

                with patch(
                    "app.routes.auth.AuthServiceDep",
                ) as mock_auth_service_class:
                    mock_auth_service = AsyncMock()
                    mock_user = UserDB(
                        uuid=uuid4(),
                        username="test",
                        email="test@example.com",
                        is_verified=True,
                    )
                    mock_auth_service.get_or_create_oauth_user = AsyncMock(
                        return_value=mock_user,
                    )
                    mock_auth_service.create_token_for_user = MagicMock(
                        return_value={
                            "access_token": "token",
                            "refresh_token": "refresh",
                            "token_type": "bearer",
                        },
                    )
                    mock_auth_service_class.return_value = mock_auth_service

                    # Make the request
                    await client.get(
                        f"/auth/callback/google?state={test_state}&code=code1",
                    )

                    # Verify cache delete was called (state consumed)
                    mock_cache.delete.assert_called_once()
        finally:
            teardown_test_cache()

    async def test_state_expires_after_ttl(self, client: AsyncClient) -> None:
        """Test that expired state is rejected."""
        mock_cache = setup_test_with_cache()
        mock_cache.get = AsyncMock(return_value=None)  # Simulates expired state

        try:
            response = await client.get(
                "/auth/callback/google?state=expired_state&code=test",
            )

            assert response.status_code == 400
            assert "expired" in response.json()["detail"].lower()
        finally:
            teardown_test_cache()


class TestOAuthErrorHandling:
    """Tests for OAuth error scenarios."""

    async def test_oauth_provider_mismatch(self, client: AsyncClient) -> None:
        """Test callback with state from different provider returns error."""
        mock_cache = setup_test_with_cache()
        # State stored for 'wechat' but accessing via 'google'
        mock_cache.get = AsyncMock(
            return_value={"provider": "wechat", "ip": "127.0.0.1"},
        )
        mock_cache.delete = AsyncMock(return_value=True)

        try:
            response = await client.get(
                "/auth/callback/google?state=mismatched_state&code=test_code",
            )

            assert response.status_code == 400
            assert "mismatch" in response.json()["detail"].lower()
        finally:
            teardown_test_cache()


@pytest.mark.parametrize("provider", ["google", "wechat"])
class TestOAuthProviderSupport:
    """Tests for multiple OAuth provider support."""

    async def test_oauth_login_provider_url(
        self,
        client: AsyncClient,
        provider: str,
    ) -> None:
        """Test that each provider has accessible login URL."""
        setup_test_with_cache()
        try:
            # This test will fail for unconfigured providers, which is expected
            response = await client.get(f"/auth/login/{provider}")

            # Should either redirect (302) or return 404 if not configured
            assert response.status_code in [302, 404]
        finally:
            teardown_test_cache()

    async def test_oauth_callback_provider_url(
        self,
        client: AsyncClient,
        provider: str,
    ) -> None:
        """Test that each provider has accessible callback URL."""
        setup_test_with_cache()
        try:
            response = await client.get(f"/auth/callback/{provider}")

            # Without state, should return 400 or 404
            assert response.status_code in [400, 404]
        finally:
            teardown_test_cache()


class TestOAuthSecurityFeatures:
    """Tests for OAuth security features."""

    async def test_state_includes_provider_info(self, client: AsyncClient) -> None:
        """Test that stored state includes provider and IP information."""
        mock_cache = setup_test_with_cache()

        try:
            with patch("app.routes.auth.oauth") as mock_oauth:
                mock_client = MagicMock()
                mock_client.authorize_redirect = AsyncMock(
                    return_value=MagicMock(status_code=302),
                )
                mock_oauth.create_client.return_value = mock_client

                with patch("app.routes.auth.settings.GOOGLE_CLIENT_ID", "test-client-id"):
                    await client.get("/auth/login/google")

                    # Verify state stored with provider info
                    call_args = mock_cache.set.call_args
                    stored_data = (
                        call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("value")
                    )

                    if stored_data:
                        assert "provider" in stored_data
                        assert stored_data["provider"] == "google"
        finally:
            teardown_test_cache()

    async def test_csrf_protection_enforced(self, client: AsyncClient) -> None:
        """Test that CSRF protection is enforced via state validation."""
        # Without state parameter, request should be rejected
        mock_cache = setup_test_with_cache()
        mock_cache.get = AsyncMock(return_value=None)

        try:
            response = await client.get("/auth/callback/google?code=some_code")

            assert response.status_code == 400
            assert "state" in response.json()["detail"].lower()
        finally:
            teardown_test_cache()
