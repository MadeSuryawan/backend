from asyncio import run
from logging import INFO, basicConfig
from pathlib import Path
from sys import path

# Add the project root to sys.path to allow importing 'app'
path.append(f"{Path(__file__).parent.parent}")

from app.clients import EmailClient
from app.errors import SendingError

# Setup simple logging to see what happens
basicConfig(level=INFO)


async def send_real_email() -> None:
    print("--- Initializing Client ---")
    client = EmailClient()

    print("--- Sending Email ---")
    try:
        # We use the async method, just like the real app
        response = await client.send_email(
            subject="Manual Script Test",
            body="If you read this, the Python integration works! Try hitting Reply.",
            reply_to="jhondoe@gmail.com",  # <--- Added this required argument
        )
        print("✅ Success! Gmail API Response:")
        print(response)
    except SendingError as e:
        print("❌ Failed!")
        print(e)


if __name__ == "__main__":
    run(send_real_email())
