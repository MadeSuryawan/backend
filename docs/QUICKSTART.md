# Quick Start Guide

Get started with the FastAPI Redis Cache in 5 minutes.

## Prerequisites

- Python 3.11 or higher
- Redis 6.0 or higher (optional, for distributed caching)
- `uv` (recommended) or `pip`

## Installation

1. **Clone the project**:

    ```bash
    git clone https://github.com/your-repo/fastapi-redis-caching.git
    cd fastapi-redis-caching
    ```

2. **Install dependencies**:

    ```bash
    # Using uv (recommended)
    uv pip install -e ".[dev]"

    # Or using pip
    pip install -e ".[dev]"
    ```

## Running the Application

1. **Start Redis (Optional)**:
    If you have a Redis server, make sure it's running. You can use Docker for a quick setup:

    ```bash
    docker run -d -p 6379:6379 -p 8081:8081 redis/redis-stack:latest
    ```

    This also provides a Redis Commander UI at `http://localhost:8081`.

    > **Note**: If Redis is not available, the application will automatically fall back to a temporary in-memory cache.

2. **Create a `.env` file**:
    Copy the `.env.example` to `.env` if it exists, or create a new one. The default settings should work with a local Redis instance.

3. **Run the FastAPI server**:

    ```bash
    python main.py
    ```

    The server will start with auto-reload.

4. **Access the API**:
    - **API Docs (Swagger)**: `http://localhost:8000/docs`
    - **Health Check**: `http://localhost:8000/health`

## Basic Usage

### 1. Caching an Endpoint

Decorate your FastAPI route with `@cached` to automatically cache its response.

```python
# In app/main.py
from app.decorators.caching import cached
from app.managers.cache_manager import cache_manager

@app.get("/items/{item_id}")
@cached(cache_manager, ttl=300, namespace="items")
async def get_item(item_id: int):
    # This function will only run on a cache miss
    print(f"Fetching item {item_id} from the database...")
    return {"item_id": item_id, "name": f"Item {item_id}"}
```

### 2. Busting the Cache on Updates

Use the `@cache_busting` decorator on endpoints that modify data to invalidate the cache. By default, it clears the entire namespace.

```python
# In app/main.py
from app.decorators.caching import cache_busting

@app.post("/items")
@cache_busting(cache_manager, namespace="items")
async def create_item(item: dict):
    # This will clear the "items" namespace after execution
    print(f"Creating item: {item}")
    return {"status": "created", "item": item}
```

### 3. Manual Cache Operations

You can interact with the `cache_manager` directly for more granular control.

```python
from app.managers.cache_manager import cache_manager

async def some_function():
    # Set a value
    await cache_manager.set("user:123", {"name": "John Doe"}, ttl=3600, namespace="users")

    # Get a value
    user = await cache_manager.get("user:123", namespace="users")

    # Delete a key
    await cache_manager.delete("user:123", namespace="users")
```

## Testing the Cache

### Step 1: First Request (Cache Miss)

Open your terminal and make a request to a cached endpoint.

```bash
curl http://localhost:8000/items/1
```

In the server logs, you will see the "Fetching item..." message, indicating the function body was executed.

### Step 2: Second Request (Cache Hit)

Make the same request again.

```bash
curl http://localhost:8000/items/1
```

The response will be served instantly from the cache (Redis or in-memory), and you will **not** see the "Fetching item..." message in the logs.

### Step 3: Check Cache Statistics

Visit the statistics endpoint to see the hit/miss ratio.

```bash
curl http://localhost:8000/cache/stats
```

You should see `{"hits":1,"misses":1,...}`.

### Step 4: Bust the Cache

Call an endpoint decorated with `@cache_busting`.

```bash
curl -X POST http://localhost:8000/items \
  -H "Content-Type: application/json" \
  -d '{"id": 2, "name": "Test Item"}'
```

### Step 5: Verify Cache was Busted

Make a request to the original cached endpoint again.

```bash
curl http://localhost:8000/items/1
```

You will see the "Fetching item..." message again, as the cache for the "items" namespace was cleared.

## Next Steps

1. **Explore the Architecture**: Read `docs/ARCHITECTURE.md` for a deep dive into the components.
2. **Review Configuration Options**: See `docs/CONFIGURATION.md` for all available settings.
3. **Run the Tests**: Execute `pytest` in your terminal to run the full test suite.
