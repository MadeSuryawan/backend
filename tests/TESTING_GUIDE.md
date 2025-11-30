# Testing Guide: Different Conftest.py Approaches

This guide explains the different testing strategies used in this project's test suite, specifically focusing on when and why to use mocking vs. real instances in fixtures.

---

## Overview

Our test suite uses two different approaches in `conftest.py` files:

1. **Mocked Approach** (`tests/clients/conftest.py`) - For testing with external dependencies
2. **Real Instance Approach** (`tests/cache/conftest.py`) - For testing internal components

---

## Approach 1: Mocked Testing (Email Client Tests)

### File: `tests/clients/conftest.py`

### Code Example

```python
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

@pytest.fixture
def mock_email_client() -> Generator[MagicMock]:
    """Mock the EmailClient to avoid sending real emails."""
    mock_client = MagicMock(spec=EmailClient)
    mock_client.send_email.return_value = {
        "id": "mock_msg_123", 
        "threadId": "mock_thread_123"
    }
    yield mock_client

@pytest.fixture
def client(mock_email_client: MagicMock) -> Generator[TestClient]:
    """Create test client with mocked email dependency."""
    app.dependency_overrides[get_email_client] = lambda: mock_email_client
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

### Why Use Mocking Here?

| Reason | Explanation |
|--------|-------------|
| **External API** | EmailClient connects to Gmail API - we can't use it in tests |
| **Requires Credentials** | Needs OAuth2 tokens from Google, not available in CI/CD |
| **Network Dependency** | Tests would fail if Google servers are down |
| **Side Effects** | Would send real emails during testing ❌ |
| **Cost** | Gmail API has rate limits and potential costs |
| **Speed** | External API calls are slow compared to mocks |

### What Gets Tested

✅ **API endpoint logic** - routes handle requests correctly  
✅ **Request validation** - Pydantic schemas work  
✅ **Error handling** - exceptions are caught and returned properly  
✅ **Dependency injection** - FastAPI DI system works  
❌ **Actual email sending** - can't test without real credentials

### Key Components

- **`TestClient`** - Synchronous test client from FastAPI
- **`MagicMock`** - Creates fake objects with controllable behavior
- **`dependency_overrides`** - FastAPI's way to inject mocks

---

## Approach 2: Real Instance Testing (Cache Tests)

### File: `tests/cache/conftest.py`

### Code Example

```python
from httpx import AsyncClient, ASGITransport

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Create async HTTP client with real app instance."""
    limiter.enabled = False
    await global_cache_manager.initialize()
    async with AsyncClient(
        base_url="http://test",
        transport=ASGITransport(app=app),
    ) as ac:
        yield ac
    await global_cache_manager.shutdown()

@pytest.fixture
async def cache_manager() -> AsyncGenerator[CacheManager]:
    """Create real cache manager instance."""
    manager = CacheManager()
    await manager.initialize()
    await manager.clear()
    manager.reset_statistics()
    yield manager
    await manager.shutdown()

@pytest.fixture
def memory_client() -> MemoryClient:
    """Create real in-memory cache client."""
    return MemoryClient()
```

### Why Use Real Instances Here?

| Reason | Explanation |
|--------|-------------|
| **Internal Code** | CacheManager is our code, fully under our control |
| **No External API** | Uses in-memory cache or local Redis (optional) |
| **No Credentials** | Doesn't need authentication or secrets |
| **No Side Effects** | Safe to run - just memory operations |
| **Fast** | All operations are local and instant |
| **Integration Testing** | Want to test actual behavior, not mocks |

### What Gets Tested

✅ **Actual cache operations** - set, get, delete work correctly  
✅ **TTL expiration** - time-to-live logic functions  
✅ **Serialization** - data marshaling works  
✅ **Statistics tracking** - hit/miss counting accurate  
✅ **Error handling** - edge cases handled properly  
✅ **Fallback behavior** - memory cache works when Redis unavailable

### Key Components

- **`AsyncClient`** - Async HTTP client from httpx (better async support)
- **Real `CacheManager`** - Actual implementation, not mocked
- **Lifecycle Management** - Initialize/shutdown handled in fixture

---

## Comparison Table

| Aspect | Email Tests (Mocked) | Cache Tests (Real) |
|--------|---------------------|-------------------|
| **Client Type** | `TestClient` (sync) | `AsyncClient` (async) |
| **Instance** | `MagicMock` | Real classes |
| **Dependency Override** | Yes | No |
| **External Services** | Gmail API | None |
| **Test Type** | Unit tests | Integration tests |
| **Speed** | Very fast | Fast |
| **Setup Complexity** | Medium | Low |
| **Test Coverage** | API contract | Full behavior |

---

## TestClient vs AsyncClient

### TestClient (Synchronous)

```python
from fastapi.testclient import TestClient

with TestClient(app) as client:
    response = client.post("/endpoint", json={...})  # Synchronous
    assert response.status_code == 200
```

**When to use:**

- Simple, synchronous tests
- Don't need async/await
- Testing straightforward CRUD endpoints

### AsyncClient (Asynchronous)

```python
from httpx import AsyncClient, ASGITransport

async with AsyncClient(transport=ASGITransport(app=app)) as client:
    response = await client.post("/endpoint", json={...})  # Async
    assert response.status_code == 200
```

**When to use:**

- Testing async routes
- Need proper async context
- Testing multiple concurrent requests
- Better represents real production behavior

---

## Decision Tree: When to Mock?

```plain text
Does the component use external services?
│
├─ YES → Use Mocks
│   ├─ Third-party APIs (Gmail, Stripe, etc.)
│   ├─ Databases in some cases
│   └─ File system operations
│
└─ NO → Use Real Instances
    ├─ Your own business logic
    ├─ In-memory operations
    └─ Local utilities
```

### Mock When

1. ❌ External API that costs money or has rate limits
2. ❌ Requires credentials you don't have in CI/CD
3. ❌ Network calls that are slow or unreliable
4. ❌ Operations with side effects (send email, charge credit card)
5. ❌ Third-party services you don't control

### Use Real Instances When

1. ✅ Your own code you want to integration test
2. ✅ Fast local operations (in-memory, disk I/O)
3. ✅ No external dependencies
4. ✅ Safe to run repeatedly without side effects
5. ✅ Testing actual behavior matters more than isolation

---

## Best Practices

### 1. Keep Fixtures DRY (Don't Repeat Yourself)

```python
# ❌ Bad - Duplicated in every test file
@pytest.fixture
def cache_manager():
    manager = CacheManager()
    yield manager

# ✅ Good - Centralized in conftest.py
# All tests in the directory can use it
```

### 2. Proper Cleanup

```python
# ✅ Always clean up resources
@pytest.fixture
async def cache_manager():
    manager = CacheManager()
    try:
        await manager.initialize()
        yield manager
    finally:
        await manager.shutdown()  # Guaranteed cleanup
```

### 3. Clear Fixture Names

```python
# ✅ Good naming
@pytest.fixture
def mock_email_client():  # Clear it's a mock
    ...

@pytest.fixture  
def cache_manager():  # Clear it's real
    ...
```

### 4. Document Fixture Purpose

```python
@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """
    Create async HTTP client for testing FastAPI endpoints.
    
    Automatically disables rate limiting and manages cache lifecycle.
    Use this for integration tests of API endpoints.
    """
    ...
```

---

## Common Patterns

### Pattern 1: Dependency Override (for mocking)

```python
# Override FastAPI dependency with mock
app.dependency_overrides[get_email_client] = lambda: mock_email_client

# Don't forget to clear after test
app.dependency_overrides.clear()
```

### Pattern 2: Fixture Composition

```python
# Fixture can depend on another fixture
@pytest.fixture
def client(mock_email_client: MagicMock):
    """Client fixture uses mock_email_client fixture"""
    ...
```

### Pattern 3: Async Fixtures

```python
@pytest.fixture
async def async_resource():
    """Use async for resources that need await"""
    resource = await create_resource()
    yield resource
    await resource.cleanup()
```

---

## Testing Philosophy

### Unit Tests (Email Tests)

**Goal:** Test individual components in isolation

```python
def test_endpoint(client: TestClient, mock_email_client: MagicMock):
    response = client.post("/send", json={...})
    
    # Verify the mock was called correctly
    mock_email_client.send_email.assert_called_once()
    assert response.status_code == 200
```

### Integration Tests (Cache Tests)  

**Goal:** Test components working together

```python
async def test_cache_operations(cache_manager: CacheManager):
    # Test real behavior
    await cache_manager.set("key", {"data": "value"})
    result = await cache_manager.get("key")
    
    # Verify actual data flow
    assert result == {"data": "value"}
```

---

## Summary

| Use Case | Approach | Example |
|----------|----------|---------|
| Testing Gmail integration | Mock EmailClient | Email tests |
| Testing cache behavior | Real CacheManager | Cache tests |
| Testing payment processing | Mock Stripe | Payment tests |
| Testing business logic | Real instances | Logic tests |
| Testing database queries | Real DB or Mock | Depends on complexity |

**Golden Rule:** Mock what you don't control, test what you own. 🎯

---

## Further Reading

- [Pytest Fixtures Documentation](https://docs.pytest.org/en/stable/fixture.html)
- [FastAPI Testing Guide](https://fastapi.tiangolo.com/tutorial/testing/)
- [unittest.mock Documentation](https://docs.python.org/3/library/unittest.mock.html)
- [HTTPX Async Client](https://www.python-httpx.org/async/)
