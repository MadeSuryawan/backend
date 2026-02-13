# Timezone Implementation Guide

## Overview

This document provides a complete guide to the timezone handling implementation in the BaliBlissed backend. The system automatically detects user timezones during registration (via header or IP fallback) and displays datetime fields in the user's local time while keeping server logs in Bali timezone (WITA).

---

## Key Features

| Feature                    | Description                                                                                         |
| -------------------------- | --------------------------------------------------------------------------------------------------- |
| **Efficient Detection**    | Middleware detects via header (zero latency). IP Geolocation used only during registration.         |
| **Single Source of Truth** | Timezone is stored **only** on the user record (`UserDB`). Blogs/Reviews use the author's timezone. |
| **Standardized Responses** | API returns UTC (ISO 8601), Local (Formatted), and Human-friendly strings.                          |
| **Dual timezone**          | User sees local time; Admin logs see Bali time (WITA).                                              |

---

## Architecture

### Data Flow

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          TIMEZONE DATA FLOW                                 │
└─────────────────────────────────────────────────────────────────────────────┘

USER REQUEST
     │
     │ POST /auth/register
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIMEZONEMIDDLEWARE (Lightweight)                                            │
│                                                                             │
│  1. Check X-Client-Timezone header                                          │
│  2. If present -> request.state.user_timezone = header_value                │
│  3. If missing -> request.state.user_timezone = "UTC"                       │
│                                                                             │
│  (No external API calls here)                                               │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ AUTH ROUTE (/auth/register)                                                 │
│                                                                             │
│  1. Check request.state.user_timezone                                       │
│  2. If "UTC" AND we have Client IP -> Call GeoTimezoneService               │
│     (Async call to ipgeolocation.io, with graceful fallback)                │
│  3. Create User with final resolved timezone                                │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ DATABASE                                                                    │
│                                                                             │
│  users table:                                                               │
│  ┌──────────┬─────────────────────┬─────────────────────────┐               │
│  │ username │      timezone       │       created_at        │               │
│  ├──────────┼─────────────────────┼─────────────────────────┤               │
│  │ johndoe  │ America/New_York    │ 2026-02-13 15:00:00 UTC │               │
│  └──────────┴─────────────────────┴─────────────────────────┘               │
│                                                                             │
│  (Blogs & Reviews tables do NOT store timezone)                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Details

### 1. Database Schema

Timezone is stored **exclusively** in the `users` table.

#### Users Table

```sql
CREATE TABLE users (
    uuid UUID PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    timezone VARCHAR(50),           -- Stores IANA timezone name
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    -- ...
);
```

### 2. TimezoneMiddleware

**File:** `app/middleware/timezone.py`

Simplified to be non-blocking and header-dependent only.

```python
class TimezoneMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Priority 1: Header. Priority 2: "UTC"
        request.state.user_timezone = request.headers.get("X-Client-Timezone", "UTC")
        return await call_next(request)
```

### 3. GeoTimezoneService

**File:** `app/services/geo_timezone.py`

Dedicated service for IP-based detection, used only when necessary (e.g., registration without header).

```python
async def detect_timezone_by_ip(client_ip: str) -> str:
    """Queries ipgeolocation.io. Returns IANA timezone or 'UTC' on failure."""
    # ... implementation using httpx ...
```

### 4. Response Schema

**File:** `app/schemas/datetime.py`

Shared `DateTimeResponse` schema used across all models (User, Blog, Review).

```python
class DateTimeResponse(BaseModel):
    utc: str       # "2026-02-13T15:00:00+00:00" (ISO 8601 with offset)
    local: str     # "Friday, February 13, 2026 10:00 AM" (Human readable)
    human: str     # "Just now", "2 hours ago"
    timezone: str  # "America/New_York"
```

---

## Frontend Integration

### Sending Timezone Header

The frontend **must** send the user's timezone in the `X-Client-Timezone` header for best accuracy.

```javascript
// Register user
const response = await fetch('/auth/register', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Client-Timezone': Intl.DateTimeFormat().resolvedOptions().timeZone
  },
  body: JSON.stringify(userData)
});
```

---

## Migration

To apply the database changes (removing redundant timezone columns from blogs/reviews):

```bash
./scripts/migrate.sh upgrade
```

---

## Files Structure

| Component | File Location | Purpose |
|String | `app/utils/timezone.py` | Formatting & Humanization logic |
| Middleware | `app/middleware/timezone.py` | Header extraction only |
| Service | `app/services/geo_timezone.py` | specific IP-based detection |
| Schema | `app/schemas/datetime.py` | DateTime response model |
| Model | `app/models/user.py` | Stores `timezone` column |

---
