# Plan: Add Testimonial Column to UserDB

## Problem Statement

Add a `testimonial` column to the `UserDB` model to allow users to store their testimonial/review text.

## Current State

- `UserDB` model exists in `app/models/user.py`
- Model uses SQLModel with PostgreSQL via `asyncpg`
- Alembic manages all migrations (schema authority)
- Existing optional profile fields follow the pattern: `Field(default=None, sa_column=Column(String(N)))`

## Proposed Changes

### 1. Update UserDB Model (`app/models/user.py`)

Add testimonial field after existing profile fields (around line 106, after `country`):

```python
testimonial: str | None = Field(
    default=None,
    sa_column=Column(String(500)),
    description="User testimonial or review text",
)
```

**Design decisions:**

- **Type:** `str | None` (optional, using pipe operator per Python 3.10+ convention)
- **Max length:** 500 characters (adjustable based on requirements)
- **Nullable:** Yes (not all users will have testimonials)
- **No index:** Text testimonials are typically not queried directly

### 2. Generate Alembic Migration

Run migration script after model update:

```bash
./scripts/migrate.sh generate "add_user_testimonial_column"
```

### 3. Review Generated Migration

Verify the migration script:

- Contains `op.add_column('users', sa.Column('testimonial', sa.String(500), nullable=True))`
- Does NOT contain any `op.drop_column` or `op.drop_table` operations
- Migration is reversible with proper downgrade function

### 4. Apply Migration

```bash
./scripts/migrate.sh upgrade
```

### 5. Add Testimonial Schema (`app/schemas/user.py`)

Add request schema for testimonial operations:

```python
class TestimonialUpdate(BaseModel):
    """Testimonial update model for user testimonial."""

    model_config = ConfigDict(populate_by_name=True)

    testimonial: str | None = Field(
        default=None,
        max_length=500,
        description="User testimonial or review text",
    )
```

Update `UserResponse` to include testimonial field.

### 6. Create PATCH Endpoint (`app/routes/user.py`)

Add new endpoint for posting/updating user testimonial:

**Endpoint:** `PATCH /users/{user_id}/testimonial`

```python
@router.patch(
    "/{user_id}/testimonial",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    status_code=HTTP_200_OK,
    summary="Update user testimonial",
    description="Update testimonial for an authenticated user.",
    responses={
        200: {"description": "Testimonial updated successfully"},
        403: {"description": "Not authorized to update this user's testimonial"},
        404: {"description": "User not found"},
        429: {"description": "Rate limit exceeded"},
    },
    operation_id="users_update_testimonial",
)
@timed("/users/{user_id}/testimonial")
@limiter.limit(lambda key: "10/hour" if "apikey" in key else "5/hour")
@cache_busting(
    key_builder=lambda user_id, **kw: [user_id_key(user_id)],
    namespace="users",
)
async def update_testimonial(
    request: Request,
    response: Response,
    user_id: UUID,
    payload: Annotated[TestimonialUpdate, Body(...)],
    repo: UserRepoDep,
    current_user: UserDBDep,
) -> UserResponse:
    """Update user testimonial."""
    db_user = await _get_authorized_user(repo, user_id, current_user, "testimonial")
    updated_user = await repo.update(user_id, {"testimonial": payload.testimonial})
    await _invalidate_user_cache(request, user_id, db_user.username)
    return db_user_to_response(updated_user)
```

**Design decisions:**

- Uses `PATCH` (partial update for single field)
- Requires authentication (owner or admin)
- Follows existing rate limiting and caching patterns
- Invalidates user cache after update

### 7. Create Unit Tests (`tests/routes/test_user_testimonial.py`)

Create comprehensive tests following existing patterns in `tests/routes/conftest.py`:

```python
"""Unit tests for user testimonial endpoint."""

import pytest
from httpx import AsyncClient
from uuid import uuid4

from app.models import UserDB


@pytest.mark.asyncio
async def test_update_testimonial_success(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
) -> None:
    """Test successful testimonial update."""
    payload = {"testimonial": "Great service! Highly recommend."}
    user_id = sample_user.uuid

    response = await client.patch(
        f"/users/{user_id}/testimonial",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert "testimonial" in response.json()


@pytest.mark.asyncio
async def test_update_testimonial_unauthorized(
    client: AsyncClient,
    sample_user: UserDB,
) -> None:
    """Test testimonial update without authentication."""
    payload = {"testimonial": "Test testimonial"}

    response = await client.patch(
        f"/users/{sample_user.uuid}/testimonial",
        json=payload,
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_testimonial_forbidden(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test testimonial update for another user (non-admin)."""
    other_user_id = uuid4()
    payload = {"testimonial": "Test testimonial"}

    response = await client.patch(
        f"/users/{other_user_id}/testimonial",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code in (403, 404)


@pytest.mark.asyncio
async def test_update_testimonial_validation_error(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
) -> None:
    """Test testimonial update with invalid data (too long)."""
    payload = {"testimonial": "x" * 501}  # Exceeds 500 char limit

    response = await client.patch(
        f"/users/{sample_user.uuid}/testimonial",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_testimonial_clear(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
) -> None:
    """Test clearing testimonial by setting to None."""
    payload = {"testimonial": None}

    response = await client.patch(
        f"/users/{sample_user.uuid}/testimonial",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 200
```

### 8. Validation Steps

- Run `uv run ruff check --fix` for linting
- Run `uv run pyrefly check .` for type checking
- Run `uv run pytest tests/routes/test_user_testimonial.py -v` for new tests
- Run `uv run pytest` to ensure all tests pass

## Notes

- No new model file created, so no `__init__.py` import update needed
- No GIN index required (not a JSONB column, not searched)
- Existing `ReviewCreate` schema in `app/schemas/review.py` handles full reviews with ratings; this testimonial is simpler (text only)
- Tests use existing fixtures from `tests/routes/conftest.py` (`client`, `sample_user`, `auth_headers`)
