from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.errors import SendingError

# Note: We do NOT need to import 'app' or 'mock_email_client' here.
# Pytest finds them automatically in 'conftest.py'.


def test_contact_support_success(client: TestClient, mock_email_client: MagicMock) -> None:
    """
    Scenario: User sends valid data.

    Expected: 200 OK, EmailClient called once.
    """
    # Added email field
    payload = {
        "subject": "Login Issue",
        "message": "I cannot access my dashboard.",
        "email": "alice@example.com",
    }

    response = client.post("/email/contact-support/", json=payload)

    # 1. Check HTTP Response
    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Email sent successfully"}

    # 2. Verify Internal Call
    mock_email_client.send_email.assert_called_once()

    # Optional: Verify exact arguments passed to the client
    call_args = mock_email_client.send_email.call_args
    assert "Login Issue" in call_args.kwargs["subject"]
    # Check that reply_to was passed correctly
    assert call_args.kwargs["reply_to"] == "alice@example.com"


def test_contact_background_success(client: TestClient, mock_email_client: MagicMock) -> None:
    """
    Scenario: User uses the background endpoint.

    Expected: 200 OK immediately.
    """
    # Added email field
    payload = {
        "subject": "Weekly Report",
        "message": "Attached is the PDF.",
        "email": "bob@example.com",
    }

    response = client.post("/email/contact-background/", json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "Email queued for sending.",
    }

    # TestClient automatically runs background tasks before finishing the request
    mock_email_client.send_email.assert_called_once()


def test_validation_error_missing_field(client: TestClient) -> None:
    """
    Scenario: User sends empty JSON or missing fields.

    Expected: 422 Unprocessable Entity (FastAPI handles this auto-magically).
    """
    # Missing 'message' and 'email' field
    payload = {"subject": "I have no message"}

    response = client.post("/email/contact-support/", json=payload)

    assert response.status_code == 422
    data = response.json()
    # It might report multiple missing fields now, so we check if at least one is reported
    assert data["detail"][0]["msg"] == "Field required"


def test_google_api_failure(client: TestClient, mock_email_client: MagicMock) -> None:
    """
    Scenario: Google API is down or credentials fail.

    Expected: 502 Bad Gateway (SendingError returns this status code).
    """
    # 1. Simulate a specific SendingError
    mock_email_client.send_email.side_effect = SendingError("Google API unavailable")

    # Added email field
    payload = {
        "subject": "Crash Test",
        "message": "This should fail.",
        "email": "crash@test.com",
    }

    response = client.post("/email/contact-support/", json=payload)

    # 2. Ensure our API handles it gracefully
    assert response.status_code == 502

    # The exception handler returns just the error message string
    assert response.json() == "Google API unavailable"
