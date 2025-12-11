from app.routes.ai import get_email_client
from app.routes.ai import router as ai_router
from app.routes.blog import router as blog_router
from app.routes.cache import get_cache_manager
from app.routes.cache import router as cache_router
from app.routes.email import router as email_router
from app.routes.items import router as items_router
from app.routes.limiter import router as limiter_router
from app.routes.user import router as user_router

__all__ = [
    "cache_router",
    "email_router",
    "get_cache_manager",
    "items_router",
    "ai_router",
    "get_email_client",
    "limiter_router",
    "blog_router",
    "user_router",
]
