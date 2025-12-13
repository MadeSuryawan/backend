from logging import getLogger
from pathlib import Path
from sys import exit as sys_exit
from sys import path
from typing import cast

from google_auth_oauthlib.flow import InstalledAppFlow

# Add the project root to sys.path to allow importing 'app'
path.append(f"{Path(__file__).parent.parent}")

from app.configs import settings
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))


def generate_token() -> None:
    """Run the OAuth2 flow to generate a token.json file."""

    if not settings.GMAIL_CLIENT_SECRET_FILE.exists():
        logger.error(
            f"Client secret file not found at: {settings.GMAIL_CLIENT_SECRET_FILE}. "
            "Please download it from Google Cloud Console.",
        )
        sys_exit(1)

    if settings.GMAIL_TOKEN_FILE.exists():
        logger.warning(
            f"A token file already exists at: {settings.GMAIL_TOKEN_FILE}. "
            "Running this will overwrite it.",
        )
        confirm = input("Type 'yes' to overwrite: ")
        if confirm.lower() != "yes":
            logger.info("Operation cancelled.")
            return

    logger.info("Starting OAuth flow. Your browser should open shortly...")

    try:
        # We use cast() here to force the type checker to recognize this
        # as an InstalledAppFlow, not a generic Flow.
        flow = cast(
            InstalledAppFlow,
            InstalledAppFlow.from_client_secrets_file(
                str(settings.GMAIL_CLIENT_SECRET_FILE),
                scopes=settings.GMAIL_SCOPES,
            ),
        )

        # Now Pyrefly knows 'flow' has this method
        creds = flow.run_local_server(port=0)

        with open(settings.GMAIL_TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

        logger.info(f"Success! Token saved to {settings.GMAIL_TOKEN_FILE}")

    except Exception:
        logger.exception("Failed to generate token")
        sys_exit(1)


if __name__ == "__main__":
    generate_token()
