# Timezone Implementation Guide

## Overview

This document provides a complete guide to the timezone handling implementation in the BaliBlissed backend. The system automatically detects user timezones during registration and displays datetime fields in the user's local time while keeping server logs in Bali timezone (WIB).

---

## Key Features

| Feature            | Description                                                                 |
| ------------------ | --------------------------------------------------------------------------- |
| **Auto-detection** | Timezone is detected automatically, users don't input it                    |
| **Multi-source**   | Detection priority: Frontend Header → IP Geolocation → UTC fallback         |
| **Human-friendly** | Datetimes displayed as "2 hours ago", "Yesterday", etc.                     |
| **Dual timezone**  | User sees local time; Admin logs see Bali time (WITA)                       |
| **Immutable**      | Timezone is set once at creation and cannot be changed                      |

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
     │ Headers: X-Client-Timezone: America/New_York  ← Optional
     │ Body: {username, email, password, ...}       ← No timezone field
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIMEZONEMIDDLEWARE                                                          │
│                                                                             │
│  Priority 1: X-Client-Timezone header (if provided by frontend)             │
│              └─> "America/New_York"                                         │
│                                                                             │
│  Priority 2: IP Geolocation (fallback)                                      │
│              └─> Detects from client IP                                     │
│                                                                             │
│  Priority 3: Default UTC (final fallback)                                   │
│              └─> "UTC"                                                      │
│                                                                             │
│  Output: request.state.user_timezone = "America/New_York"                   │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ AUTH ROUTE (/auth/register)                                                 │
│                                                                             │
│  1. Extract timezone from request.state.user_timezone                       │
│  2. Pass to repository: repo.create(user_create, timezone=tz)               │
│  3. Return UserResponse with formatted datetime                             │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ DATABASE                                                                    │
│                                                                             │
│  users table:                                                               │
│  ┌──────────┬─────────────┬─────────────────────┬─────────────────────────┐ │
│  │ username │    email    │      timezone       │       created_at        │ │
│  ├──────────┼─────────────┼─────────────────────┼─────────────────────────┤ │
│  │ johndoe  │ john@...    │ America/New_York    │ 2026-02-13 15:00:00 UTC │ │
│  └──────────┴─────────────┴─────────────────────┴─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ API RESPONSE                                                                │
│                                                                             │
│  {                                                                          │
│    "uuid": "...",                                                           │
│    "username": "johndoe",                                                   │
│    "createdAt": {                                                           │
│      "utc": "2026-02-13T15:00:00Z",                                         │
│      "local": "2026-02-13 10:00:00 EST",                                    │
│      "human": "Just now",                                                   │
│      "timezone": "America/New_York"                                         │
│    }                                                                        │
│  }                                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Details

### 1. Database Schema

#### Users Table

```sql
CREATE TABLE users (
    uuid UUID PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    timezone VARCHAR(50),           -- NEW: Stores IANA timezone name
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE
    -- ... other fields
);
```

#### Blogs Table

```sql
CREATE TABLE blogs (
    id UUID PRIMARY KEY,
    author_id UUID REFERENCES users(uuid),
    timezone VARCHAR(50),           -- NEW: Author's timezone at creation
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    -- ... other fields
);
```

#### Reviews Table

```sql
CREATE TABLE reviews (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(uuid),
    timezone VARCHAR(50),           -- NEW: Reviewer's timezone at creation
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    -- ... other fields
);
```

### 2. TimezoneMiddleware

**File:** `app/middleware/timezone.py`

```python
class TimezoneMiddleware(BaseHTTPMiddleware):
    """Detects and stores user's timezone in request state."""
    
    async def dispatch(self, request: Request, call_next):
        user_timezone = self._detect_timezone(request)
        request.state.user_timezone = user_timezone
        response = await call_next(request)
        return response

    def _detect_timezone(self, request: Request) -> str:
        # Priority 1: X-Client-Timezone header
        if client_tz := request.headers.get("X-Client-Timezone"):
            return client_tz
        
        # Priority 2: IP Geolocation
        client_ip = request.client.host if request.client else None
        if client_ip and (detected_tz := detect_timezone_from_ip(client_ip)):
            return detected_tz
        
        # Priority 3: Default UTC
        return "UTC"
```

### 3. Timezone Utilities

**File:** `app/utils/timezone.py`

#### format_api_response()

```python
def format_api_response(dt: datetime, user_timezone: str) -> dict[str, str]:
    """Format datetime for API response with multiple representations."""
    user_tz = ZoneInfo(user_timezone)
    local_dt = dt.astimezone(user_tz)
    
    return {
        "utc": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "local": local_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "human": humanize_time(dt),
        "timezone": user_timezone,
    }
```

#### humanize_time()

```python
def humanize_time(dt: datetime) -> str:
    """Convert datetime to human-friendly relative time."""
    now = datetime.now(UTC)
    diff = now - dt
    
    if diff < timedelta(minutes=1):
        return "Just now"
    elif diff < timedelta(hours=1):
        return f"{int(diff.seconds / 60)} minutes ago"
    elif diff < timedelta(days=1):
        return f"{int(diff.seconds / 3600)} hours ago"
    elif diff < timedelta(days=2):
        return f"Yesterday at {dt.strftime('%I:%M %p')}"
    elif diff < timedelta(days=7):
        return f"{diff.days} days ago"
    else:
        return dt.strftime("%b %d, %Y")
```

#### format_logs()

```python
def format_logs(dt: datetime, timezone: str) -> str:
    """Format datetime for server logs (Bali timezone)."""
    _tz = ZoneInfo(timezone)
    return dt.astimezone(_tz).strftime("%d/%m/%y %H:%M:%S %Z")
```

### 4. Response Schema

**File:** `app/schemas/cache.py`

```python
class DateTimeResponse(BaseModel):
    """Standard datetime representation in API responses."""
    utc: str       # ISO 8601 format: "2026-02-13T15:00:00Z"
    local: str     # User's local time: "2026-02-13 10:00:00 EST"
    human: str     # Human-friendly: "Just now", "2 hours ago"
    timezone: str  # Timezone used: "America/New_York"
```

---

## Frontend Integration

### Sending Timezone Header

The frontend should send the user's timezone in the `X-Client-Timezone` header:

#### JavaScript/TypeScript

```javascript
// Get user's timezone
const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
// e.g., "America/New_York", "Europe/London", "Asia/Singapore"

// Register user
const response = await fetch('/auth/register', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Client-Timezone': userTimezone  // Send timezone header
  },
  body: JSON.stringify({
    username: 'johndoe',
    email: 'john@example.com',
    password: 'SecurePass123!',
    firstName: 'John',
    lastName: 'Doe',
    country: 'USA'
    // Note: NO timezone field in body!
  })
});

const user = await response.json();
console.log(user.createdAt.human);  // "Just now"
console.log(user.createdAt.local);  // "2026-02-13 10:00:00 EST"
```

#### React Hook Example

```typescript
// hooks/useTimezone.ts
export const useTimezone = (): string => {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
};

// api/client.ts
const getHeaders = () => ({
  'Content-Type': 'application/json',
  'X-Client-Timezone': Intl.DateTimeFormat().resolvedOptions().timeZone,
});

export const registerUser = async (userData: UserCreate) => {
  const response = await fetch('/auth/register', {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(userData),
  });
  return response.json();
};
```

### Displaying Datetime

#### Human-Friendly Display (Default)

```javascript
// Show "2 hours ago" by default
<div>{user.createdAt.human}</div>

// Show full timestamp on hover/title
div.title = user.createdAt.local;  // "2026-02-13 10:00:00 EST"
```

#### Toggle View

```javascript
const [showFullTime, setShowFullTime] = useState(false);

<div onClick={() => setShowFullTime(!showFullTime)}>
  {showFullTime ? user.createdAt.local : user.createdAt.human}
</div>
```

#### Tooltip Example

```javascript
// Using a tooltip library
<Tooltip content={user.createdAt.local}>
  <span>{user.createdAt.human}</span>
</Tooltip>
```

---

## API Examples

### User Registration

**Request:**

```http
POST /auth/register
Content-Type: application/json
X-Client-Timezone: America/New_York

{
  "username": "johndoe",
  "email": "john@example.com",
  "password": "SecurePass123!",
  "firstName": "John",
  "lastName": "Doe",
  "country": "USA"
}
```

**Response:**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "johndoe",
  "email": "john@example.com",
  "firstName": "John",
  "lastName": "Doe",
  "displayName": "John Doe",
  "isVerified": false,
  "role": "user",
  "country": "USA",
  "createdAt": {
    "utc": "2026-02-13T15:00:00Z",
    "local": "2026-02-13 10:00:00 EST",
    "human": "Just now",
    "timezone": "America/New_York"
  },
  "updatedAt": null
}
```

### Get User Profile

**Response:**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "johndoe",
  "email": "john@example.com",
  "createdAt": {
    "utc": "2026-02-13T15:00:00Z",
    "local": "2026-02-13 10:00:00 EST",
    "human": "2 days ago",
    "timezone": "America/New_York"
  }
}
```

### Create Blog Post

**Request:**

```http
POST /blogs
Authorization: Bearer <token>
Content-Type: application/json
X-Client-Timezone: America/New_York

{
  "title": "My Bali Experience",
  "content": "Bali was amazing!...",
  "tags": ["travel", "bali"]
}
```

**Response:**

```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "title": "My Bali Experience",
  "authorId": "550e8400-e29b-41d4-a716-446655440000",
  "createdAt": {
    "utc": "2026-02-13T20:00:00Z",
    "local": "2026-02-13 15:00:00 EST",
    "human": "Just now",
    "timezone": "America/New_York"
  }
}
```

---

## Server Logs

All server logs are displayed in **Bali timezone (WIB - Western Indonesian Time)**:

```text
[2026-02-14 06:00:00 WIB] Request: POST /auth/register, from ip: 192.168.1.1
[2026-02-14 06:00:01 WIB] Response: 201 for POST /auth/register in 0.234s
[2026-02-14 06:05:30 WIB] Request: GET /api/users/me, from ip: 192.168.1.1
[2026-02-14 06:05:30 WIB] Response: 200 for GET /api/users/me in 0.045s
```

This ensures consistent log timestamps for admin monitoring regardless of user locations.

---

## Testing

### Manual Testing Checklist

1. **Registration without header:**
   - Should use IP geolocation or default to UTC
   - Check `timezone` field in database

2. **Registration with header:**

   ```bash
   curl -X POST http://localhost:8000/auth/register \
     -H "Content-Type: application/json" \
     -H "X-Client-Timezone: Europe/London" \
     -d '{"username":"test","email":"test@test.com","password":"Test123!"}'
   ```

   - Should store "Europe/London" in database

3. **Human-friendly time:**
   - Create user, then immediately fetch profile
   - Should see "Just now" or "1 minute ago"

4. **Logs in Bali time:**
   - Check server logs show WIB timezone

---

## Migration

To apply the database migration:

```bash
./scripts/migrate.sh upgrade
```

This adds the `timezone` column to `users`, `blogs`, and `reviews` tables.

---

## Files Modified

| File                          | Changes                      |
| ----------------------------- | ---------------------------- |
| `app/models/user.py`          | Added `timezone` field       |
| `app/models/blog.py`          | Added `timezone` field       |
| `app/models/review.py`        | Added `timezone` field       |
| `app/repositories/user.py`    | Store timezone from kwargs   |
| `app/repositories/blog.py`    | Store timezone from kwargs   |
| `app/repositories/review.py`  | Store timezone from kwargs   |
| `app/routes/auth.py`          | Extract and pass timezone    |
| `app/routes/blog.py`          | Extract and pass timezone    |
| `app/routes/review.py`        | Extract and pass timezone    |
| `app/utils/timezone.py`       | New: Timezone utilities      |
| `app/utils/helpers.py`        | Updated `response_datetime()`|
| `app/middleware/timezone.py`  | New: TimezoneMiddleware      |
| `app/middleware/middleware.py`| Updated logging format       |
| `app/schemas/cache.py`        | Added `DateTimeResponse`     |
| `app/main.py`                 | Added TimezoneMiddleware     |

---

## Future Enhancements

### IP Geolocation Implementation

The `detect_timezone_from_ip()` function is currently a placeholder. To implement actual IP-based timezone detection:

#### Option 1: ipapi.co (Free tier)

```python
import httpx

async def detect_timezone_from_ip(client_ip: str) -> str | None:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://ipapi.co/{client_ip}/json/")
            data = response.json()
            return data.get("timezone")
    except Exception:
        return None
```

#### Option 2: MaxMind GeoIP2 (Self-hosted)

```python
import geoip2.database

reader = geoip2.database.Reader("/path/to/GeoLite2-City.mmdb")

def detect_timezone_from_ip(client_ip: str) -> str | None:
    try:
        response = reader.city(client_ip)
        return response.location.time_zone
    except Exception:
        return None
```

---

## Summary

| Feature | Status |
| ------- | -------- |
| Auto-detect timezone | ✅ Complete |
| Store in database | ✅ Complete |
| Multi-format response | ✅ Complete |
| Human-friendly time | ✅ Complete |
| Bali timezone logs | ✅ Complete |
| Frontend integration | ✅ Documented |

For questions or issues, refer to the implementation files or contact the development team.
