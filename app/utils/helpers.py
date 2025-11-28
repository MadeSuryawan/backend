from collections.abc import MutableMapping
from datetime import datetime
from logging import INFO, FileHandler, Formatter, Logger, NullHandler
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute, Match, Route

from app.configs import settings

# from app.models.blog import BlogDB
# from app.models.user import UserDB


def today_str() -> str:
    """Return today's date as a string."""
    # return datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    return datetime.now(datetime.now().astimezone().tzinfo).strftime(
        "%Y-%m-%d %H:%M:%S",
    )


def file_logger(logger: Logger) -> Logger:
    """Log to file."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = FileHandler(log_dir / "app.log") if settings.LOG_TO_FILE else NullHandler()
    file_handler.setLevel(INFO)
    formatter = Formatter("%(asctime)s - %(filename)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


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
            # pyrefly: ignore [missing-attribute]
            summary = route.summary
            break
        if is_route and route.matches(scope)[0] == Match.FULL:
            # pyrefly: ignore [missing-attribute]
            summary = route.name
            break

    return summary


# def response_datetime(db: UserDB | BlogDB) -> dict[str, Any]:
#     """Format datetime for response.

#     Args:
#         db: Database model

#     Returns:
#         dict[str, Any]: Dictionary with formatted datetimes
#     """
#     date_format = "%Y-%m-%d %H:%M:%S"
#     db_dict = db.model_dump()

#     db_dict["created_at"] = db.created_at.astimezone().strftime(date_format)

#     db_dict["updated_at"] = "No updates"
#     if updated := db.updated_at:
#         db_dict["updated_at"] = updated.astimezone().strftime(date_format)

#     return db_dict
