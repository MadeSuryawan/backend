from collections.abc import MutableMapping
from datetime import datetime
from logging import Logger
from time import perf_counter
from typing import Any

from anyio import Path
from bs4 import BeautifulSoup
from bs4.exceptions import ParserRejectedMarkup
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.routing import APIRoute
from markdown import markdown
from mdformat import text as mdformat_text
from starlette.routing import BaseRoute, Match, Route

from app.models.blog import BlogDB
from app.models.user import UserDB


def host(request: Request) -> str:
    """Return the host IP address."""
    return request.client.host if request.client else "unknown"


def today_str() -> str:
    """Return today's date as a string."""
    # return datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    return datetime.now(datetime.now().astimezone().tzinfo).strftime(
        "%Y-%m-%d %H:%M:%S",
    )


def time_taken(start_time: float) -> str:
    minutes, seconds = divmod(perf_counter() - start_time, 60)
    formatted_time = f"{int(minutes)}m {int(seconds)}s"

    return formatted_time


def get_summary(request: Request) -> str | None:
    """Extract route summary from request."""

    scope: MutableMapping[str, Any] = request.scope
    app: FastAPI = scope["app"]
    routes: list[BaseRoute] = app.routes

    summary = None
    for route in routes:
        is_api_route = type(route) is APIRoute
        is_route = type(route) is Route
        if is_api_route and route.matches(scope)[0] == Match.FULL:
            summary = route.summary
            break
        if is_route and route.matches(scope)[0] == Match.FULL:
            summary = route.name
            break

    return summary


def response_datetime(db: UserDB | BlogDB) -> dict[str, Any]:
    """
    Format datetime for response.

    Args:
        db: Database model

    Returns:
        dict[str, Any]: Dictionary with formatted datetimes
    """
    date_format = "%Y-%m-%d %H:%M:%S"
    db_dict = db.model_dump()

    db_dict["created_at"] = db.created_at.astimezone().strftime(date_format)

    db_dict["updated_at"] = "No updates"
    if updated := db.updated_at:
        db_dict["updated_at"] = updated.astimezone().strftime(date_format)

    return db_dict


async def clean_markdown(text: str, logger: Logger) -> str:
    """
    Format raw Markdown text to be CommonMark/GFM compliant.

    Useful for standardizing AI outputs before sending to frontend.
    """
    try:
        return await run_in_threadpool(
            mdformat_text,
            text,
            extensions={"gfm"},  # 1. Enable Plugins: Explicitly list extensions that installed
            options={  # 2. Options: Customize how the text is rendered
                "wrap": "no",  # 'no' is best for Frontends (let CSS handle wrapping)
                "number": True,  # Use ordered numbering (1. 2. 3.) instead of auto (1. 1. 1.)
                "end_of_line": "lf",  # Use Unix line endings (LF)
            },
        )
    except Exception:
        # Fallback: If formatting fails (rare), return original text
        # so the user still gets their answer.
        logger.exception("Markdown formatting failed")
        return text


def md_to_text(text: str) -> str:
    """
    Convert Markdown text to plain text (removing Markdown syntax).

    Uses BeautifulSoup to extract text content, which is safer and cleaner
    than regex for removing complex Markdown formatting.
    """
    if not text:
        return ""

    try:
        # 1. Parse Markdown to HTML
        html_content = markdown(text)

        # 2. Extract Text using BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")

        # Prepend "- " to list items to preserve structure, handling indentation for nested lists
        for li in soup.find_all("li"):
            # Calculate depth based on parent ul/ol tags
            depth = len(list(li.find_parents(["ul", "ol"])))
            indent = "  " * (depth - 1)
            li.string = f"{indent}- {li.get_text()}"

        plain_text = soup.get_text()

        return plain_text.strip()
    except ParserRejectedMarkup:
        # Fallback to original text if conversion fails
        return text


async def save_to_file(data: str, file_path: Path) -> None:
    """
    Write the itinerary to a file.

    Args:
        data: The data string to write.
        file_path: The path to the file to write to.
    """
    async with await file_path.open("w") as f:
        await f.write(data)
