# BaliBlissed Backend - AI Agent Guide

This document provides essential information for AI coding agents working on the BaliBlissed Backend project.

## Project Overview

BaliBlissed Backend is a production-ready FastAPI application serving a Bali travel agency. It provides RESTful APIs for user management, blog posts, reviews, AI-powered itinerary generation, email inquiries, and media handling with robust caching and rate limiting.

**Key Characteristics:**

- **Framework:** FastAPI with async/await patterns
- **Database:** PostgreSQL with SQLModel (SQLAlchemy 2.0+)
- **Cache:** Redis with in-memory fallback
- **AI Integration:** Google Gemini for chatbot and itinerary generation
- **Authentication:** JWT-based with OAuth (Google, WeChat) support
- **File Storage:** Cloudinary (production) or local filesystem (development)

## Technology Stack

| Component | Technology |
| --------- | ---------- |
| Python | 3.13+ |
| Web Framework | FastAPI 0.121+ |
| Database | PostgreSQL + asyncpg |
| ORM | SQLModel 0.0.27+ |
| Migrations | Alembic |
| Cache | Redis 7+ |
| Rate Limiting | slowapi |
| Package Manager | uv |
| Testing | pytest + pytest-asyncio |
| Linting | ruff |
| AI Client | google-genai |
| Auth | python-jose + passlib (Argon2) |

## Project Structure

```text
backend/
├── app/                      # Main application package
│   ├── auth/                 # Authentication utilities and permissions
│   ├── clients/              # External service clients (AI, Email, Redis)
│   ├── configs/              # Settings and configuration
│   ├── data/                 # Static data/statistics
│   ├── db/                   # Database engine, session, initialization
│   ├── decorators/           # Custom decorators (caching, retry, metrics)
│   ├── dependencies/         # FastAPI dependency injection
│   ├── errors/               # Custom exceptions and handlers
│   ├── managers/             # Business logic managers (cache, rate limiter, tokens)
│   ├── middleware/           # FastAPI middleware (CORS, logging, security)
│   ├── models/               # SQLModel database models
│   ├── repositories/         # Database access layer (Repository pattern)
│   ├── routes/               # API route handlers (controllers)
│   ├── schemas/              # Pydantic models for request/response
│   ├── services/             # Business logic services
│   └── utils/                # Utility functions
├── alembic/                  # Database migration scripts
├── tests/                    # Test suite (mirrors app structure)
├── scripts/                  # Shell scripts for development
├── secrets/                  # Environment files and credentials (gitignored)
├── uploads/                  # Local file uploads (development)
└── logs/                     # Application logs
```

## Architecture Patterns

### 1. Layered Architecture

The application follows a clean layered architecture:

```text
Routes (Controllers) → Services → Repositories → Models
       ↓                    ↓            ↓
   Schemas            Business Logic   Database
```

### 2. Repository Pattern

All database operations go through repository classes inheriting from `BaseRepository[ModelT, CreateSchemaT, UpdateSchemaT]`:

```python
# Example: app/repositories/user.py
class UserRepository(BaseRepository[UserDB, UserCreate, UserUpdate]):
    model = UserDB
    id_field = "uuid"  # Users use UUID, not 'id'
```

### 3. Dependency Injection

FastAPI dependencies are defined in `app/dependencies/`:

- `UserDBDep` - Get current authenticated user
- `UserRepoDep` - Get UserRepository instance
- `CacheDep` - Get CacheManager instance
- `EmailDep` - Get EmailClient instance

### 4. Custom Exceptions

All errors use custom exceptions in `app/errors/`:

- `DatabaseError` with subtypes (DuplicateEntryError, RecordNotFoundError)
- `UserAuthenticationError` for auth failures
- `CacheExceptionError` for cache operations
- `EmailServiceError` for email failures
- `AiError` for AI client errors

Each exception has a corresponding FastAPI exception handler.

## Build and Development Commands

### Prerequisites

- Python 3.13+
- PostgreSQL (local or Neon)
- Docker and Docker Compose
- uv (`pip install uv`)

### Environment Setup

```bash
# Copy example environment
cp .env.example secrets/.env

# Edit secrets/.env with your configuration
# Required: DATABASE_URL, SECRET_KEY
# Optional: GEMINI_API_KEY, Cloudinary credentials
```

### Running the Application

#### Option 1: Using the run script (recommended for development)

```bash
# Start all services (Postgres, Redis, Backend)
./scripts/run.sh start

# Stop services
./scripts/run.sh stop
```

#### Option 2: Manual with uv

```bash
# Install dependencies
uv sync

# Activate virtual environment
source .venv/bin/activate

# Run migrations
uv run alembic upgrade head

# Start server with auto-reload
uv run uvicorn app.main:app --reload --loop uvloop
```

#### Option 3: Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f backend
```

### Database Migrations

```bash
# Generate a new migration
./scripts/migrate.sh generate "add_new_column"

# Apply migrations
./scripts/migrate.sh upgrade

# Downgrade one revision
./scripts/migrate.sh downgrade -1

# Check current revision
./scripts/migrate.sh current

# View migration history
./scripts/migrate.sh history
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=app --cov-report=html

# Run specific test file
uv run pytest tests/auth/test_token_manager.py -v

# Run with asyncio debugging
uv run pytest --asyncio-mode=auto -v
```

### Test Structure

- Tests mirror the `app/` structure
- Each test module has its own `conftest.py` for fixtures
- Uses `httpx.AsyncClient` with `ASGITransport` for endpoint testing
- Mock external services (Redis, Email, AI) in unit tests

### Test Configuration (pytest.ini)

- `asyncio_mode = auto` - Automatic async test detection
- `--cov=app` - Coverage for app package
- `--strict-markers` - Require explicit markers

## Code Style Guidelines

### Linting and Formatting

The project uses **ruff** with strict configuration:

```bash
# Check all files
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .

# Format code
uv run ruff format .
```

### Key Style Rules

- **Line length:** 100 characters
- **Quotes:** Double quotes for strings
- **Imports:** Sorted with isort rules, no relative imports (`TID252`)
- **Type hints:** Required for all function parameters and returns (`ANN`)
- **Docstrings:** Google style (not strictly enforced for all modules)

### Type Hints

- Use `` for forward references
- Use built-in generics: `list[str]` not `List[str]`
- Use `|` for unions: `str | None` not `Optional[str]`
- Use `type[ModelT]` for class references

### Documentation Standards

All public functions should include:

- Docstring with description
- Args/Parameters section with types
- Returns section with type
- Raises section for exceptions
- Examples section for complex functions

Example:

```python
async def get_user_by_id(user_id: UUID) -> UserDB | None:
    """Retrieve a user by their UUID.

    Parameters
    ----------
    user_id : UUID
        The unique identifier of the user.

    Returns
    -------
    UserDB | None
        The user if found, None otherwise.

    Examples
    --------
    >>> user = await get_user_by_id(uuid.uuid4())
    >>> if user:
    ...     print(user.email)
    """
```

## Security Considerations

### Authentication

- JWT tokens with HS256 algorithm
- Access tokens expire in 30 minutes (configurable)
- Refresh tokens expire in 7 days
- Token blacklist stored in Redis for logout

### Password Security

- Argon2 password hashing with configurable security levels
- Levels: development, standard (default), high, paranoid
- Account lockout after 5 failed login attempts

### Rate Limiting

- Default: 100 requests per hour per IP
- Uses slowapi with Redis storage
- Fallback to in-memory if Redis unavailable

### Data Validation

- Pydantic models for all request/response data
- SQL injection prevention via SQLModel/SQLAlchemy
- XSS protection via FastAPI's automatic escaping

### File Uploads

- Size limits: 5MB images, 50MB videos
- Allowed types strictly validated
- Images processed with Pillow before storage
- Storage provider: local (dev) or Cloudinary (prod)

### Environment Security

- Secrets stored in `secrets/.env` (gitignored)
- Never commit credentials, tokens, or API keys
- Use strong SECRET_KEY in production (32+ chars)

## Configuration

### Key Environment Variables

```bash
# Required
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
SECRET_KEY=your-secure-secret-key-min-32-chars

# Optional
GEMINI_API_KEY=your-google-ai-api-key
REDIS_URL=redis://localhost:6379/0
STORAGE_PROVIDER=local  # or cloudinary
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```

### Settings File

All configuration is centralized in `app/configs/settings.py` using Pydantic Settings:

- Environment-specific defaults
- Validation for required fields in production
- Redis and database connection pooling config

## Common Development Tasks

### Adding a New Route

1. Create route handler in `app/routes/new_feature.py`
2. Define request/response schemas in `app/schemas/`
3. Add to `app/routes/__init__.py` exports
4. Register in `app/main.py` routes list
5. Add tests in `tests/routes/test_new_feature.py`

### Adding a Database Model

1. Create model in `app/models/new_model.py`
2. Add to `app/models/__init__.py` exports
3. Create repository in `app/repositories/new_model.py`
4. Generate migration: `./scripts/migrate.sh generate "add new_model"`
5. Apply migration: `./scripts/migrate.sh upgrade`

### Adding a New Exception Type

1. Define exception class in `app/errors/category.py`
2. Create handler function in same file
3. Export from `app/errors/__init__.py`
4. Register handler in `app/main.py` errors list

## External Service Integration

### Redis

- Used for: caching, rate limiting, token blacklist, login tracking
- In-memory fallback enabled by default for development
- Health check available at `/health`

### Google Gemini AI

- Model: gemini-2.0-flash
- Features: chatbot, itinerary generation
- Safety settings configured for medium+ threshold
- Circuit breaker pattern for resilience

### Gmail API (Email)

- OAuth2 authentication
- Credentials stored in `secrets/client_secret.json`
- Token stored in `secrets/token.json`
- Sends emails to COMPANY_TARGET_EMAIL

### Cloudinary (Production Storage)

- Image and video uploads
- Automatic optimization and transformation
- Configurable via environment variables

## Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
psql -U postgres -c '\l'

# For Neon Postgres, verify SSL settings
# Connection string format:
# postgresql+asyncpg://user:pass@host/dbname?ssl=require
```

### Redis Connection Issues

```bash
# Check Redis is running
docker-compose ps redis

# Test connection
redis-cli ping
```

### Migration Errors

```bash
# Reset migrations (dev only)
./scripts/migrate.sh reset

# Stamp existing database to current
./scripts/migrate.sh stamp head
```

## Deployment

### Docker Build

```bash
docker build -t baliblissed-backend .
docker run -p 8000:8000 --env-file secrets/.env baliblissed-backend
```

### Production Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Set strong `SECRET_KEY` (32+ characters)
- [ ] Configure `REDIS_PASSWORD`
- [ ] Set `STORAGE_PROVIDER=cloudinary` with credentials
- [ ] Configure `PRODUCTION_FRONTEND_URL` for CORS
- [ ] Run migrations: `alembic upgrade head`
- [ ] Set up log rotation for `logs/app.log`

## Resources

- **API Documentation:** <http://localhost:8000/docs> (Swagger UI)
- **Alternative Docs:** <http://localhost:8000/redoc> (ReDoc)
- **Health Check:** <http://localhost:8000/health>
- **Metrics:** <http://localhost:8000/metrics>
- **Redis UI:** <http://localhost:8081> (Redis Commander)
