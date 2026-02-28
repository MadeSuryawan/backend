import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.models import UserDB
from app.dependencies.dependencies import get_current_user, get_ai_client_state
from unittest.mock import AsyncMock, MagicMock, patch

client = TestClient(app)

# Mock AI client
mock_ai_client = MagicMock()

@pytest.fixture(autouse=True)
def setup_overrides():
    # Setup dependency overrides
    app.dependency_overrides[get_ai_client_state] = lambda: mock_ai_client
    yield
    app.dependency_overrides = {}

@pytest.mark.asyncio
async def test_chat_bot_user_id_required_for_regular_user():
    # Mock current user as regular user
    mock_user_inst = UserDB(uuid=uuid4(), role="user", is_verified=True, email="user@example.com")
    
    # Override get_current_user
    app.dependency_overrides[get_current_user] = lambda: mock_user_inst
    
    # Call without user_id
    response = client.post("/ai/chat", json={"query": "test"})
    assert response.status_code == 400
    assert response.json()["detail"] == "user_id query parameter is required for non-admin users."

@pytest.mark.asyncio
async def test_chat_bot_user_id_optional_for_admin():
    # Mock current user as admin
    mock_admin_inst = UserDB(uuid=uuid4(), role="admin", is_verified=True, email="admin@example.com")
    
    # Override get_current_user
    app.dependency_overrides[get_current_user] = lambda: mock_admin_inst
    
    with patch("app.routes.ai.chat_with_ai", new_callable=AsyncMock) as mock_chat:
        # Mocking the response model model_dump
        mock_chat_response = MagicMock()
        mock_chat_response.model_dump.return_value = {"answer": "test response"}
        mock_chat.return_value = mock_chat_response
        
        # Mock get_authorized_user to just return a dummy user
        with patch("app.routes.ai.get_authorized_user", new_callable=AsyncMock) as mock_auth:
            mock_auth.return_value = mock_admin_inst
            
            # Call without user_id as admin
            response = client.post("/ai/chat", json={"query": "test"})
            
            assert response.status_code == 200
            assert response.json()["answer"] == "test response"
