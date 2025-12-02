from asyncio import run
from logging import INFO, basicConfig
from pathlib import Path
from sys import path

from rich import print as rprint

# Add the project root to sys.path to allow importing 'app'
path.append(f"{Path(__file__).parent.parent}")

from app.clients import EmailClient
from app.errors import SendingError
from app.managers import email_circuit_breaker

# Setup simple logging to see what happens
basicConfig(level=INFO)


async def send_real_email() -> None:
    rprint("[b i blue]--- Initializing Client ---[/b i blue]")
    client = EmailClient(circuit_breaker=email_circuit_breaker)

    rprint("[b i blue]--- Sending Email ---[/b i blue]")
    try:
        # We use the async method, just like the real app
        response = await client.send_email(
            subject="Manual Script Test",
            body="If you read this, the Python integration works! Try hitting Reply.",
            reply_to="jhoncena@gmail.com",  # <--- Added this required argument
        )
        rprint("✅ [b i green]Success![/b i green] Gmail API Response:")
        rprint(response)
    except SendingError as e:
        rprint("❌ [b i red]Failed![/b i red]")
        rprint(e)


if __name__ == "__main__":
    run(send_real_email())
