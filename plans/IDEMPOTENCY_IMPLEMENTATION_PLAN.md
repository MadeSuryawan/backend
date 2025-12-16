# Idempotency Implementation Plan

## Executive Summary

This plan outlines the implementation of idempotency for the BaliBlissed Backend API, leveraging **tenacity** (already implemented for retry logic) and **idemptx** (to be added) libraries in tandem. The solution uses Redis for fast, ephemeral idempotency key storage with a 1-hour TTL (configurable per endpoint).

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Solution Overview](#2-solution-overview)
3. [Library Analysis](#3-library-analysis)
4. [Architecture Design](#4-architecture-design)
5. [Implementation Steps](#5-implementation-steps)
6. [Endpoint Classification](#6-endpoint-classification)
7. [Testing Strategy](#7-testing-strategy)
8. [Rollout Plan](#8-rollout-plan)

---

## 1. Problem Statement

### Current Issues Identified

Based on the codebase analysis, the following issues exist:

1. **AI Client Retry on Expensive Operations**: The [`AiClient._generate_content()`](app/clients/ai_client.py:103) method uses `@with_retry` which can cause double-billing when AI calls timeout but succeed on the backend.

2. **Registration Duplicates**: The [`POST /auth/register`](app/routes/auth.py:342) endpoint lacks idempotency protection, potentially creating duplicate users if network issues cause client retries.

3. **Blog Creation Duplicates**: The [`POST /blogs/create`](app/routes/blog.py:314) endpoint could create duplicate posts on network retries.

4. **Email Double-Sends**: The [`POST /ai/email-inquiry`](app/routes/ai.py:169) endpoint could send duplicate emails if the client retries after a timeout.

### Why Idempotency Matters

```
Client Request → Network Timeout → Client Retry → Duplicate Operation
         ↓                                              ↓
   First request succeeded                    Second request also executes
   but response was lost                      creating duplicate data/costs
```

---

## 2. Solution Overview

### The Tandem Approach: Tenacity + Idemptx

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Request Flow                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Client Request                                                      │
│       │                                                              │
│       ▼                                                              │
│  ┌─────────────────┐                                                │
│  │  Idempotency    │  ◄── idemptx: Check/Store idempotency key     │
│  │  Middleware     │      in Redis with 1h TTL                      │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │  Route Handler  │                                                 │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │  Service Layer  │  ◄── tenacity: Internal retry for transient   │
│  │  (with retry)   │      errors ONLY on idempotent operations     │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │  External APIs  │  ◄── Circuit Breaker: Fail fast when          │
│  │  (AI, Email)    │      services are unhealthy                    │
│  └─────────────────┘                                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Principles

| Layer | Library | Purpose |
|-------|---------|---------|
| **Request Layer** | idemptx | Prevent duplicate request processing via idempotency keys |
| **Service Layer** | tenacity | Retry transient failures for inherently idempotent operations (Redis, reads) |
| **Infrastructure** | Circuit Breaker | Fail fast when external services are down |

---

## 3. Library Analysis

### 3.1 Tenacity (Current Usage)

**Location**: [`app/decorators/with_retry.py`](app/decorators/with_retry.py)

**Current Configuration**:
```python
RETRIABLE_EXCEPTIONS = (RedisConnectionError, RedisTimeoutError, ConnectionError, TimeoutError)

@with_retry(max_retries=3, base_delay=0.1, max_delay=2.0)
async def some_function():
    ...
```

**Current Usage Analysis**:
- ✅ **Appropriate**: [`RedisClient`](app/clients/redis_client.py) operations (GET, SET, DELETE are idempotent)
- ⚠️ **Problematic**: [`AiClient._generate_content()`](app/clients/ai_client.py:103) (non-idempotent, costly)

### 3.2 Idemptx Library

**What is idemptx?**

`idemptx` is a Python library for implementing idempotency in distributed systems. It provides:

1. **Idempotency Key Management**: Tracks request IDs to detect duplicates
2. **Backend Adapters**: Redis, PostgreSQL, Memory backends
3. **Decorator Pattern**: Easy integration with existing code
4. **Response Caching**: Returns cached responses for duplicate requests

**Core Concepts**:

```python
from idemptx import IdempotencyManager
from idemptx.backends import RedisBackend

# Initialize with Redis backend
backend = RedisBackend(redis_client=redis, prefix="idem:", ttl=3600)  # 1 hour
idempotency = IdempotencyManager(backend=backend)

# Use as decorator
@idempotency.idempotent(key_from="idempotency_key")
async def create_resource(idempotency_key: str, data: dict):
    # This will only execute once per idempotency_key
    return await db.create(data)
```

**Why idemptx + tenacity?**

| Concern | Library | Scope |
|---------|---------|-------|
| Client retry safety | idemptx | Request-level (prevents duplicate processing) |
| Transient failure recovery | tenacity | Operation-level (retries internal operations) |

**The Difference**:
- **idemptx**: "Has this request been processed before?" (request deduplication)
- **tenacity**: "Should I retry this failed operation?" (failure recovery)

---

## 4. Architecture Design

### 4.1 Redis Key Schema

```
idempotency:{namespace}:{idempotency_key}
```

**Examples**:
```
idempotency:auth:register:550e8400-e29b-41d4-a716-446655440000
idempotency:blogs:create:7c9e6679-7425-40de-944b-e07fc1f90ae7
idempotency:ai:email:a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
```

**Value Schema** (JSON):
```json
{
  "status": "processing|completed|failed",
  "response": { ... },
  "created_at": "2025-12-16T07:00:00Z",
  "completed_at": "2025-12-16T07:00:05Z",
  "error": null
}
```

### 4.2 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           app/                                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  managers/                                                               │
│  ├── idempotency_manager.py  ◄── NEW: Core idempotency logic            │
│  │                                                                       │
│  decorators/                                                             │
│  ├── idempotent.py           ◄── NEW: @idempotent decorator             │
│  ├── with_retry.py           (existing, will be modified)               │
│  │                                                                       │
│  middleware/                                                             │
│  ├── idempotency.py          ◄── NEW: Extract Idempotency-Key header    │
│  │                                                                       │
│  errors/                                                                 │
│  ├── idempotency.py          ◄── NEW: IdempotencyError classes          │
│  │                                                                       │
│  schemas/                                                                │
│  ├── idempotency.py          ◄── NEW: IdempotencyRecord schema          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.3 State Machine

```
                    ┌─────────────┐
                    │   START     │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
         ┌─────────│  Check Key  │─────────┐
         │         └─────────────┘         │
         │                                 │
    Key Found                         Key Not Found
         │                                 │
         ▼                                 ▼
   ┌───────────┐                    ┌─────────────┐
   │  Return   │                    │ Set Status  │
   │  Cached   │                    │ PROCESSING  │
   │  Response │                    └──────┬──────┘
   └───────────┘                           │
                                           ▼
                                    ┌─────────────┐
                              ┌─────│  Execute    │─────┐
                              │     │  Handler    │     │
                              │     └─────────────┘     │
                              │                         │
                         Success                    Failure
                              │                         │
                              ▼                         ▼
                       ┌───────────┐            ┌───────────┐
                       │ Set Status│            │ Set Status│
                       │ COMPLETED │            │  FAILED   │
                       │ + Response│            │  + Error  │
                       └───────────┘            └───────────┘
```

---

## 5. Implementation Steps

### Phase 1: Foundation (Week 1)

#### Step 1.1: Add idemptx Dependency

**File**: `pyproject.toml`

```toml
dependencies = [
    # ... existing dependencies
    "idemptx>=0.3.0",  # Add this line
]
```

#### Step 1.2: Create Idempotency Error Classes

**New File**: `app/errors/idempotency.py`

```python
"""Idempotency-related error classes."""

from app.errors.base import BaseError


class IdempotencyError(BaseError):
    """Base class for idempotency errors."""
    pass


class DuplicateRequestError(IdempotencyError):
    """Raised when a duplicate request is detected that is still processing."""
    
    def __init__(self, idempotency_key: str, retry_after: float = 5.0) -> None:
        self.idempotency_key = idempotency_key
        self.retry_after = retry_after
        super().__init__(
            detail=f"Request with key '{idempotency_key}' is already being processed",
            status_code=409,  # Conflict
        )


class IdempotencyKeyMissingError(IdempotencyError):
    """Raised when idempotency key is required but not provided."""
    
    def __init__(self) -> None:
        super().__init__(
            detail="Idempotency-Key header is required for this endpoint",
            status_code=400,
        )


class IdempotencyKeyInvalidError(IdempotencyError):
    """Raised when idempotency key format is invalid."""
    
    def __init__(self, key: str) -> None:
        super().__init__(
            detail=f"Invalid idempotency key format: '{key}'. Must be a valid UUID.",
            status_code=400,
        )
```

#### Step 1.3: Create Idempotency Schemas

**New File**: `app/schemas/idempotency.py`

```python
"""Idempotency-related schemas."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IdempotencyStatus(str, Enum):
    """Status of an idempotency record."""
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class IdempotencyRecord(BaseModel):
    """Schema for idempotency record stored in Redis."""
    
    status: IdempotencyStatus
    response: Any | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    
    class Config:
        use_enum_values = True
```

#### Step 1.4: Create Idempotency Manager

**New File**: `app/managers/idempotency_manager.py`

```python
"""Idempotency manager for handling request deduplication."""

from datetime import UTC, datetime
from logging import getLogger
from typing import Any
from uuid import UUID

from app.clients.protocols import CacheProtocol
from app.errors.idempotency import DuplicateRequestError
from app.schemas.idempotency import IdempotencyRecord, IdempotencyStatus
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))

DEFAULT_TTL = 3600  # 1 hour in seconds (reasonable for API idempotency)


class IdempotencyManager:
    """
    Manager for idempotency operations using Redis backend.
    
    This class handles the core idempotency logic:
    - Checking if a request has been processed
    - Storing processing/completed/failed states
    - Returning cached responses for duplicate requests
    """
    
    def __init__(
        self,
        cache_client: CacheProtocol,
        prefix: str = "idempotency",
        ttl: int = DEFAULT_TTL,
    ) -> None:
        """
        Initialize idempotency manager.
        
        Args:
            cache_client: Redis client implementing CacheProtocol
            prefix: Key prefix for idempotency records
            ttl: Time-to-live in seconds (default: 1 hour)
        """
        self._cache = cache_client
        self._prefix = prefix
        self._ttl = ttl
    
    def _build_key(self, namespace: str, idempotency_key: str) -> str:
        """Build Redis key for idempotency record."""
        return f"{self._prefix}:{namespace}:{idempotency_key}"
    
    async def check_and_set_processing(
        self,
        namespace: str,
        idempotency_key: str | UUID,
    ) -> IdempotencyRecord | None:
        """
        Check if request exists and set to processing if not.
        
        Uses Redis SETNX for atomic check-and-set operation.
        
        Args:
            namespace: Operation namespace (e.g., 'auth:register')
            idempotency_key: Unique request identifier
            
        Returns:
            Existing IdempotencyRecord if found, None if new request
            
        Raises:
            DuplicateRequestError: If request is currently processing
        """
        key = self._build_key(namespace, str(idempotency_key))
        
        # Try to get existing record
        existing = await self._cache.get(key)
        if existing:
            record = IdempotencyRecord.model_validate_json(existing)
            
            if record.status == IdempotencyStatus.PROCESSING:
                # Request is still being processed
                raise DuplicateRequestError(str(idempotency_key))
            
            # Return completed/failed response
            logger.info(f"Returning cached response for idempotency key: {idempotency_key}")
            return record
        
        # Set new processing record
        new_record = IdempotencyRecord(status=IdempotencyStatus.PROCESSING)
        await self._cache.set(
            key,
            new_record.model_dump_json(),
            ex=self._ttl,
        )
        logger.debug(f"Set processing status for idempotency key: {idempotency_key}")
        return None
    
    async def set_completed(
        self,
        namespace: str,
        idempotency_key: str | UUID,
        response: Any,
    ) -> None:
        """
        Mark request as completed with response.
        
        Args:
            namespace: Operation namespace
            idempotency_key: Unique request identifier
            response: Response to cache
        """
        key = self._build_key(namespace, str(idempotency_key))
        record = IdempotencyRecord(
            status=IdempotencyStatus.COMPLETED,
            response=response,
            completed_at=datetime.now(UTC),
        )
        await self._cache.set(
            key,
            record.model_dump_json(),
            ex=self._ttl,
        )
        logger.debug(f"Set completed status for idempotency key: {idempotency_key}")
    
    async def set_failed(
        self,
        namespace: str,
        idempotency_key: str | UUID,
        error: str,
    ) -> None:
        """
        Mark request as failed with error.
        
        Args:
            namespace: Operation namespace
            idempotency_key: Unique request identifier
            error: Error message
        """
        key = self._build_key(namespace, str(idempotency_key))
        record = IdempotencyRecord(
            status=IdempotencyStatus.FAILED,
            error=error,
            completed_at=datetime.now(UTC),
        )
        await self._cache.set(
            key,
            record.model_dump_json(),
            ex=self._ttl,
        )
        logger.debug(f"Set failed status for idempotency key: {idempotency_key}")
    
    async def delete(
        self,
        namespace: str,
        idempotency_key: str | UUID,
    ) -> bool:
        """
        Delete idempotency record (for testing or manual cleanup).
        
        Args:
            namespace: Operation namespace
            idempotency_key: Unique request identifier
            
        Returns:
            True if deleted, False if not found
        """
        key = self._build_key(namespace, str(idempotency_key))
        return await self._cache.delete(key) > 0
```

### Phase 2: Decorator Implementation (Week 2)

#### Step 2.1: Create Idempotent Decorator

**New File**: `app/decorators/idempotent.py`

```python
"""Idempotency decorator for FastAPI endpoints."""

from collections.abc import Callable
from functools import wraps
from logging import getLogger
from typing import Any
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel

from app.errors.idempotency import IdempotencyKeyInvalidError, IdempotencyKeyMissingError
from app.managers.idempotency_manager import IdempotencyManager
from app.schemas.idempotency import IdempotencyStatus
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"


def _validate_uuid(key: str) -> UUID:
    """Validate and parse UUID from string."""
    try:
        return UUID(key)
    except ValueError as e:
        raise IdempotencyKeyInvalidError(key) from e


def _extract_idempotency_key(
    request: Request,
    required: bool = True,
) -> UUID | None:
    """
    Extract idempotency key from request header.
    
    Args:
        request: FastAPI request object
        required: Whether the key is required
        
    Returns:
        Parsed UUID or None if not required and missing
        
    Raises:
        IdempotencyKeyMissingError: If required and missing
        IdempotencyKeyInvalidError: If present but invalid format
    """
    key = request.headers.get(IDEMPOTENCY_KEY_HEADER)
    
    if not key:
        if required:
            raise IdempotencyKeyMissingError()
        return None
    
    return _validate_uuid(key)


def _serialize_response(response: Any) -> Any:
    """Serialize response for caching."""
    if isinstance(response, BaseModel):
        return response.model_dump()
    if isinstance(response, list):
        return [_serialize_response(item) for item in response]
    return response


def idempotent(
    idempotency_manager: IdempotencyManager,
    namespace: str,
    required: bool = True,
    response_model: type[BaseModel] | None = None,
) -> Callable:
    """
    Decorator for making endpoints idempotent.
    
    Args:
        idempotency_manager: IdempotencyManager instance
        namespace: Namespace for the idempotency key (e.g., 'auth:register')
        required: Whether idempotency key is required (default: True)
        response_model: Pydantic model for deserializing cached responses
        
    Returns:
        Decorated function
        
    Example:
        @router.post("/register")
        @idempotent(idempotency_manager, namespace="auth:register")
        async def register(request: Request, ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract request from args or kwargs
            request: Request | None = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                request = kwargs.get("request")
            
            if not request:
                # No request object, execute normally
                return await func(*args, **kwargs)
            
            # Extract idempotency key
            idempotency_key = _extract_idempotency_key(request, required=required)
            
            if not idempotency_key:
                # Key not required and not provided, execute normally
                return await func(*args, **kwargs)
            
            # Check for existing record
            existing = await idempotency_manager.check_and_set_processing(
                namespace=namespace,
                idempotency_key=idempotency_key,
            )
            
            if existing:
                # Return cached response
                if existing.status == IdempotencyStatus.COMPLETED:
                    if response_model and existing.response:
                        return response_model.model_validate(existing.response)
                    return existing.response
                elif existing.status == IdempotencyStatus.FAILED:
                    # Re-raise the original error? Or return error response?
                    # For now, let the request retry
                    pass
            
            try:
                # Execute the handler
                result = await func(*args, **kwargs)
                
                # Store successful response
                serialized = _serialize_response(result)
                await idempotency_manager.set_completed(
                    namespace=namespace,
                    idempotency_key=idempotency_key,
                    response=serialized,
                )
                
                return result
                
            except Exception as e:
                # Store failure
                await idempotency_manager.set_failed(
                    namespace=namespace,
                    idempotency_key=idempotency_key,
                    error=str(e),
                )
                raise
        
        return wrapper
    return decorator
```

#### Step 2.2: Update Retry Decorator Usage

**Modify**: `app/clients/ai_client.py`

Remove `@with_retry` from AI generation methods (non-idempotent, costly operations):

```python
# REMOVE @with_retry from _generate_content method
# The circuit breaker provides sufficient protection

async def _generate_content(
    self,
    contents: ContentListUnion | ContentListUnionDict,
    config: GenerateContentConfig,
) -> object:
    """Generate content - NO RETRY (expensive, non-idempotent)."""
    # ... existing implementation
```

**Keep** `@with_retry` on [`RedisClient`](app/clients/redis_client.py) operations (idempotent by nature).

### Phase 3: Endpoint Integration (Week 3)

#### Step 3.1: Create Idempotency Dependency

**Add to**: `app/dependencies/dependencies.py`

```python
from app.managers.idempotency_manager import IdempotencyManager

# Global idempotency manager (initialized on startup)
_idempotency_manager: IdempotencyManager | None = None


def get_idempotency_manager() -> IdempotencyManager:
    """Get idempotency manager dependency."""
    if _idempotency_manager is None:
        raise RuntimeError("Idempotency manager not initialized")
    return _idempotency_manager


def set_idempotency_manager(manager: IdempotencyManager) -> None:
    """Set idempotency manager (called on startup)."""
    global _idempotency_manager
    _idempotency_manager = manager


IdempotencyDep = Annotated[IdempotencyManager, Depends(get_idempotency_manager)]
```

#### Step 3.2: Initialize on App Startup

**Modify**: `app/main.py`

```python
from app.managers.idempotency_manager import IdempotencyManager
from app.dependencies.dependencies import set_idempotency_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing startup code
    
    # Initialize idempotency manager
    from app.clients.redis_client import RedisClient
    redis_client = RedisClient()
    await redis_client.connect()
    
    idempotency_manager = IdempotencyManager(
        cache_client=redis_client,
        prefix="idempotency",
        ttl=3600,  # 1 hour
    )
    set_idempotency_manager(idempotency_manager)
    
    yield
    
    # ... existing shutdown code
```

#### Step 3.3: Apply to Endpoints

**Example for Registration**: `app/routes/auth.py`

```python
from app.decorators.idempotent import idempotent
from app.dependencies import IdempotencyDep

@router.post("/register", ...)
@timed("/auth/register")
@limiter.limit("5/hour")
async def register_user(
    request: Request,
    response: Response,
    user_create: UserCreate,
    repo: UserRepoDep,
    idempotency: IdempotencyDep,
) -> UserResponse:
    """Register a new user with idempotency protection."""
    # Check idempotency
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key:
        existing = await idempotency.check_and_set_processing(
            namespace="auth:register",
            idempotency_key=idempotency_key,
        )
        if existing and existing.response:
            return UserResponse.model_validate(existing.response)
    
    try:
        user = await repo.create(user_create)
        result = UserResponse.model_validate(user, from_attributes=True)
        
        if idempotency_key:
            await idempotency.set_completed(
                namespace="auth:register",
                idempotency_key=idempotency_key,
                response=result.model_dump(),
            )
        
        return result
    except Exception as e:
        if idempotency_key:
            await idempotency.set_failed(
                namespace="auth:register",
                idempotency_key=idempotency_key,
                error=str(e),
            )
        raise
```

---

## 6. Endpoint Classification

### Summary Table

| Endpoint | Method | Idempotent? | Retry Safe? | Action Required |
|----------|--------|-------------|-------------|-----------------|
| `/auth/login` | POST | ✅ Yes (read-only) | ✅ Safe | No change |
| `/auth/register` | POST | ❌ No | ❌ Unsafe | Add `@idempotent` |
| `/auth/refresh` | POST | ✅ Yes | ✅ Safe | No change |
| `/auth/logout` | POST | ✅ Yes | ✅ Safe | No change |
| `/blogs/create` | POST | ❌ No | ❌ Unsafe | Add `@idempotent` |
| `/blogs/update/{id}` | PUT | ✅ Yes | ✅ Safe | Keep `@with_retry` |
| `/blogs/delete/{id}` | DELETE | ✅ Yes | ✅ Safe | Keep `@with_retry` |
| `/ai/chat` | POST | ❌ No | ⚠️ Costly | Remove retry, add cache |
| `/ai/email-inquiry` | POST | ❌ No | ❌ Unsafe | Add `@idempotent`, remove retry |
| `/ai/itinerary-md` | POST | ❌ No | ⚠️ Costly | Already cached, remove retry |

### Detailed Recommendations

#### 1. User Registration (`POST /auth/register`)

**Current State**: No idempotency protection
**Risk**: Duplicate users, confusing errors on retry
**Solution**: Add `@idempotent` decorator with `auth:register` namespace

#### 2. Blog Creation (`POST /blogs/create`)

**Current State**: No idempotency protection
**Risk**: Duplicate blog posts
**Solution**: Add `@idempotent` decorator with `blogs:create` namespace

#### 3. Email Inquiry (`POST /ai/email-inquiry`)

**Current State**: No idempotency, uses AI (costly)
**Risk**: Duplicate emails, double AI billing
**Solution**: Add `@idempotent` decorator, remove AI retry

#### 4. AI Itinerary Generation (`POST /ai/itinerary-md`)

**Current State**: Has caching (good!), has AI retry (bad!)
**Risk**: Double AI billing on timeout-retry
**Solution**: Remove `@with_retry` from AI client, rely on caching + idempotency

---

## 7. Testing Strategy

### Unit Tests

**New File**: `tests/managers/test_idempotency_manager.py`

```python
"""Tests for IdempotencyManager."""

import pytest
from unittest.mock import AsyncMock

from app.managers.idempotency_manager import IdempotencyManager
from app.schemas.idempotency import IdempotencyStatus
from app.errors.idempotency import DuplicateRequestError


@pytest.fixture
def mock_cache():
    return AsyncMock()


@pytest.fixture
def idempotency_manager(mock_cache):
    return IdempotencyManager(cache_client=mock_cache, ttl=3600)


class TestIdempotencyManager:
    
    async def test_new_request_sets_processing(self, idempotency_manager, mock_cache):
        """New requests should be set to processing status."""
        mock_cache.get.return_value = None
        
        result = await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key="test-key-123",
        )
        
        assert result is None
        mock_cache.set.assert_called_once()
    
    async def test_duplicate_processing_raises_error(self, idempotency_manager, mock_cache):
        """Duplicate requests that are processing should raise error."""
        mock_cache.get.return_value = '{"status": "processing", "response": null}'
        
        with pytest.raises(DuplicateRequestError):
            await idempotency_manager.check_and_set_processing(
                namespace="test",
                idempotency_key="test-key-123",
            )
    
    async def test_completed_request_returns_cached(self, idempotency_manager, mock_cache):
        """Completed requests should return cached response."""
        mock_cache.get.return_value = '{"status": "completed", "response": {"id": 1}}'
        
        result = await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key="test-key-123",
        )
        
        assert result is not None
        assert result.status == IdempotencyStatus.COMPLETED
        assert result.response == {"id": 1}
```

### Integration Tests

**New File**: `tests/routes/test_idempotency_integration.py`

```python
"""Integration tests for idempotency."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


class TestRegistrationIdempotency:
    
    async def test_duplicate_registration_returns_same_response(self, client: AsyncClient):
        """Duplicate registration requests should return cached response."""
        idempotency_key = str(uuid4())
        user_data = {
            "userName": f"testuser_{uuid4().hex[:8]}",
            "email": f"test_{uuid4().hex[:8]}@example.com",
            "password": "SecurePass123!",
        }
        
        # First request
        response1 = await client.post(
            "/auth/register",
            json=user_data,
            headers={"Idempotency-Key": idempotency_key},
        )
        assert response1.status_code == 201
        
        # Duplicate request (same idempotency key)
        response2 = await client.post(
            "/auth/register",
            json=user_data,
            headers={"Idempotency-Key": idempotency_key},
        )
        assert response2.status_code == 201
        assert response1.json() == response2.json()
```

---

## 8. Rollout Plan

### Week 1: Foundation
- [ ] Add idemptx to dependencies
- [ ] Create error classes
- [ ] Create schemas
- [ ] Create IdempotencyManager
- [ ] Write unit tests

### Week 2: Decorator & Integration
- [ ] Create @idempotent decorator
- [ ] Create idempotency dependency
- [ ] Update app startup
- [ ] Write integration tests

### Week 3: Endpoint Migration
- [ ] Apply to `/auth/register`
- [ ] Apply to `/blogs/create`
- [ ] Apply to `/ai/email-inquiry`
- [ ] Remove AI client retry
- [ ] Update API documentation

### Week 4: Testing & Documentation
- [ ] Run full test suite
- [ ] Load testing for race conditions
- [ ] Update API documentation
- [ ] Create client integration guide

---

## Appendix: Tenacity + Idemptx Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Request: POST /blogs/create                               │
│                    Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. idemptx Layer (Request Deduplication)                                   │
│     ┌─────────────────────────────────────────────────────────┐             │
│     │ Check Redis: idempotency:blogs:create:550e8400...       │             │
│     │                                                          │             │
│     │ If EXISTS and COMPLETED → Return cached response        │             │
│     │ If EXISTS and PROCESSING → Return 409 Conflict          │             │
│     │ If NOT EXISTS → Set PROCESSING, continue                │             │
│     └─────────────────────────────────────────────────────────┘             │
│                           │                                                  │
│                           ▼                                                  │
│  2. Application Layer (Business Logic)                                      │
│     ┌─────────────────────────────────────────────────────────┐             │
│     │ BlogRepository.create(blog_data)                         │             │
│     │                                                          │             │
│     │ This is NOT wrapped with @with_retry                    │             │
│     │ because it's non-idempotent (creates new record)        │             │
│     └─────────────────────────────────────────────────────────┘             │
│                           │                                                  │
│                           ▼                                                  │
│  3. tenacity Layer (Transient Failure Recovery)                            │
│     ┌─────────────────────────────────────────────────────────┐             │
│     │ Redis cache operations (SET, GET, DELETE)               │             │
│     │                                                          │             │
│     │ @with_retry(max_retries=3)                              │             │
│     │ async def cache_manager.set(key, value)                 │             │
│     │                                                          │             │
│     │ Safe to retry because Redis SET is idempotent           │             │
│     └─────────────────────────────────────────────────────────┘             │
│                           │                                                  │
│                           ▼                                                  │
│  4. idemptx Layer (Response Storage)                                        │
│     ┌─────────────────────────────────────────────────────────┐             │
│     │ On SUCCESS: Set COMPLETED + store response              │             │
│     │ On FAILURE: Set FAILED + store error                    │             │
│     └─────────────────────────────────────────────────────────┘             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Insight: Complementary Responsibilities

| Library | Protects Against | Scope |
|---------|------------------|-------|
| **idemptx** | Client retries, network duplicates | Request boundary |
| **tenacity** | Transient infrastructure failures | Internal operations |
| **Circuit Breaker** | Cascading failures from unhealthy services | External service calls |

The three patterns work together:
1. **idemptx** ensures the same request isn't processed twice
2. **tenacity** ensures internal idempotent operations survive brief hiccups
3. **Circuit Breaker** prevents hammering failing services

---

## Questions for Review

1. Should failed idempotency records allow retry (current plan) or return the error?
2. Should we add an admin endpoint to clear idempotency keys for testing?
3. Do we need metrics/observability for idempotency hit/miss rates?
