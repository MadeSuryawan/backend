"""Repository integration tests against the real PostgreSQL test database."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors.database import DuplicateEntryError
from app.repositories.blog import BlogRepository
from app.repositories.review import ReviewRepository
from app.repositories.user import UserRepository
from app.schemas.blog import BlogSchema
from app.schemas.review import ReviewCreate
from app.schemas.user import UserCreate, UserUpdate


def blog_content(topic: str) -> str:
    """Build valid long-form blog content that passes schema validation."""
    return (
        f"{topic} helps travelers plan better before they arrive in Bali. "
        "Bali visitors should pack light layers, sun protection, reusable bottles, "
        "sandals, modest temple clothing, and a small day bag. "
        "Careful itineraries mix beach mornings, rice terrace walks, local markets, "
        "and evening rest so the pace stays enjoyable. "
        "Travelers who keep spare cash, offline maps, and rain protection handle "
        "sudden weather changes more comfortably."
    )


@dataclass
class User:
    """User data for integration-test setup."""

    username: str
    email: str
    password: str = "Password123"  # noqa: S107
    first_name: str | None = None
    last_name: str | None = None


async def create_user(
    session: AsyncSession,
    deps: User,
) -> UUID:
    """Create and commit a user for integration-test setup."""
    user = await UserRepository(session).create(
        UserCreate(
            userName=deps.username,
            email=deps.email,
            password=SecretStr(deps.password),
            first_name=deps.first_name,
            last_name=deps.last_name,
        ),
    )
    await session.commit()
    return user.uuid


@pytest.mark.asyncio
async def test_user_repository_create_and_update_persist_auth_fields(
    db_session: AsyncSession,
) -> None:
    """UserRepository should hash passwords, compute names, and verify new passwords."""
    repository = UserRepository(db_session)

    created = await repository.create(
        UserCreate(
            userName="made",
            email="made@example.com",
            password=SecretStr("Password123"),
            first_name="Made",
            last_name="Surya",
        ),
        timezone="Asia/Makassar",
    )
    await db_session.commit()
    original_password_hash = created.password_hash

    assert created.password_hash is not None
    assert created.password_hash != "Password123"
    assert created.display_name == "Made Surya"
    assert created.timezone == "Asia/Makassar"
    assert await repository.do_password_verify("made", "Password123") is not None

    updated = await repository.update(
        created.uuid,
        UserUpdate(
            first_name="Komang",
            last_name="Surya",
            password=SecretStr("NewPassword123"),
            confirmed_password=SecretStr("NewPassword123"),
        ),
    )

    assert updated is not None
    assert updated.display_name == "Komang Surya"
    assert updated.password_hash != original_password_hash
    assert await repository.do_password_verify("made", "NewPassword123") is not None


@pytest.mark.asyncio
async def test_user_repository_create_maps_duplicate_email_to_conflict(
    db_session: AsyncSession,
) -> None:
    """Duplicate user emails should surface as DuplicateEntryError from Postgres."""
    repository = UserRepository(db_session)
    deps = User(
        username="first-user",
        email="shared@example.com",
    )
    await create_user(db_session, deps)

    with pytest.raises(DuplicateEntryError) as exc_info:
        await repository.create(
            UserCreate(
                userName="second-user",
                email="shared@example.com",
                password=SecretStr("Password123"),
            ),
        )

    assert "email" in exc_info.value.detail
    assert "already exists" in exc_info.value.detail


@pytest.mark.asyncio
async def test_blog_repository_create_computes_metadata_and_supports_tag_queries(
    db_session: AsyncSession,
) -> None:
    """BlogRepository should persist derived metadata and real PostgreSQL JSONB searches."""
    deps = User(
        username="writer",
        email="writer@example.com",
    )
    author_id = await create_user(db_session, deps)
    repository = BlogRepository(db_session)

    created = await repository.create(
        BlogSchema(
            authorId=author_id,
            title="Bali Packing Guide",
            slug="bali-packing-guide",
            content=blog_content("Packing early"),
            tags=["packing", "bali"],
            imagesUrl=["https://example.com/blog-media/packing-cover.jpg"],
        ),
        author_id=author_id,
    )
    any_match = await repository.create(
        BlogSchema(
            authorId=author_id,
            title="Bali Culture Tips",
            slug="bali-culture-tips",
            content=blog_content("Understanding ceremonies"),
            tags=["culture", "bali"],
        ),
        author_id=author_id,
    )
    all_match = await repository.create(
        BlogSchema(
            authorId=author_id,
            title="Bali Culture And Packing Tips",
            slug="bali-culture-and-packing-tips",
            content=blog_content("Balancing packing with etiquette"),
            tags=["culture", "packing", "bali"],
        ),
        author_id=author_id,
    )

    assert created.word_count >= 50
    assert created.reading_time_minutes >= 1
    assert created.images_url == ["https://example.com/blog-media/packing-cover.jpg"]

    matching_any = await repository.search_by_tags(["culture", "packing"])
    matching_all = await repository.search_by_tags_all(["culture", "packing"])

    assert {blog.id for blog in matching_any} == {created.id, any_match.id, all_match.id}
    assert [blog.id for blog in matching_all] == [all_match.id]


@pytest.mark.asyncio
async def test_blog_repository_create_maps_duplicate_slug_to_friendly_error(
    db_session: AsyncSession,
) -> None:
    """Duplicate blog slugs should return the repository's user-facing error message."""
    deps = User(
        username="blogger",
        email="blogger@example.com",
    )
    author_id = await create_user(db_session, deps)
    repository = BlogRepository(db_session)

    await repository.create(
        BlogSchema(
            authorId=author_id,
            title="Unique Bali Blog",
            slug="unique-bali-blog",
            content=blog_content("Writing the first post"),
            tags=["bali"],
        ),
        author_id=author_id,
    )
    await db_session.commit()

    with pytest.raises(DuplicateEntryError) as exc_info:
        await repository.create(
            BlogSchema(
                authorId=author_id,
                title="Conflicting Bali Blog",
                slug="unique-bali-blog",
                content=blog_content("Writing the second post"),
                tags=["bali", "travel"],
            ),
            author_id=author_id,
        )

    assert exc_info.value.detail == (
        "A blog with the URL 'unique-bali-blog' already exists. Please choose a different title."
    )


@pytest.mark.asyncio
async def test_review_repository_orders_queries_and_persists_image_changes(
    db_session: AsyncSession,
) -> None:
    """ReviewRepository should order newest-first and persist image list updates."""
    deps = User(
        username="reviewer",
        email="reviewer@example.com",
    )
    user_id = await create_user(db_session, deps)
    item_id = UUID("11111111-1111-1111-1111-111111111111")
    repository = ReviewRepository(db_session)

    older = await repository.create(
        ReviewCreate(item_id=item_id, rating=4, title="Solid trip", content="Loved it a lot."),
        user_id=user_id,
    )
    newer = await repository.create(
        ReviewCreate(
            item_id=item_id,
            rating=5,
            title="Amazing trip",
            content="Loved it even more.",
        ),
        user_id=user_id,
    )
    older.created_at = datetime.now(tz=UTC) - timedelta(days=1)
    newer.created_at = datetime.now(tz=UTC)
    await db_session.commit()

    user_reviews = await repository.get_by_user(user_id)
    item_reviews = await repository.get_by_item(item_id)

    assert [review.id for review in user_reviews] == [newer.id, older.id]
    assert [review.id for review in item_reviews] == [newer.id, older.id]

    updated = await repository.add_image(newer.id, "https://cdn.example.com/reviews/media-1.jpg")

    assert updated is not None
    assert updated.images_url == ["https://cdn.example.com/reviews/media-1.jpg"]
    assert await repository.remove_image_by_media_id(newer.id, "missing-media") is False
    assert await repository.remove_image_by_media_id(newer.id, "media-1") is True
    refreshed = await repository.get_by_id(newer.id)

    assert refreshed is not None
    assert refreshed.images_url is None
