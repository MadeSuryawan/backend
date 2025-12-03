"""Database models for the application."""

from app.models.blog import BlogDB
from app.models.user import UserDB

__all__ = ["UserDB", "BlogDB"]
