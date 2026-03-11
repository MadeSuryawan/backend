# OAuth API Testing Collection Documentation

This directory contains API testing collections for OAuth authentication endpoints in the BaliBlissed Backend. The collections support both **HTTPie** (command-line) and **Postman** (GUI) testing workflows.

## Table of Contents

- [Overview](#overview)
- [OAuth Authentication Flow](#oauth-authentication-flow)
- [Prerequisites and Dependencies](#prerequisites-and-dependencies)
- [Configuration](#configuration)
- [HTTPie Collection Guide](#httpie-collection-guide)
- [Postman Collection Guide](#postman-collection-guide)
- [API Endpoints Reference](#api-endpoints-reference)
- [Troubleshooting](#troubleshooting)

---

## Overview

### Files in This Directory

| File | Description |
| ---- | ----------- |
| [`oauth_httpie_collection.sh`](oauth_httpie_collection.sh) | HTTPie command-line testing script with 8 test scenarios |
| [`oauth_postman_collection.json`](oauth_postman_collection.json) | Postman collection v2.1 with environment variables and examples |
| [`README.md`](README.md) | This documentation file |

### Supported OAuth Providers

| Provider | Status | Environment Variables Required |
| -------- | ------ | ------------------------------ |
| **Google** | Active | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| **WeChat** | Pending | `WECHAT_APP_ID`, `WECHAT_APP_SECRET` |
| **Apple** | Pending | `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY_PATH` |

---

## OAuth Authentication Flow

The BaliBlissed Backend implements OAuth 2.0 with OpenID Connect (for Google) following this sequence:

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#2563eb',
    'primaryTextColor': '#ffffff',
    'primaryBorderColor': '#1d4ed8',
    'secondaryColor': '#059669',
    'secondaryTextColor': '#ffffff',
    'secondaryBorderColor': '#047857',
    'tertiaryColor': '#dc2626',
    'tertiaryTextColor': '#ffffff',
    'tertiaryBorderColor': '#b91c1c',
    'noteBkgColor': '#fef3c7',
    'noteTextColor': '#92400e',
    'noteBorderColor': '#f59e0b',
    'lineColor': '#374151',
    'textColor': '#111827',
    'activationBkgColor': '#dbeafe',
    'activationBorderColor': '#3b82f6'
  }
}}%%
sequenceDiagram
    autonumber
    participant C as Client
    participant B as Backend
    participant O as OAuth Provider

    rect rgb(219, 234, 254)
        Note over C,O: Phase 1: Login Initiation
        C->>+B: GET /auth/login/google
        B->>B: Generate state (CSRF token)
        B->>B: Store state in cache (TTL: 10 min)
        B-->>-C: 302 Redirect
        C->>+O: Redirect to OAuth provider<br/>?state=CSRF_TOKEN&code_challenge=PKCE
    end

    rect rgb(220, 252, 231)
        Note over C,O: Phase 2: User Authentication
        O->>O: User authenticates
        O->>O: User authorizes application
        O-->>-C: Redirect to callback URL
    end

    rect rgb(254, 226, 226)
        Note over C,O: Phase 3: Callback Handling
        C->>+B: GET /auth/callback/google<br/>?state=CSRF_TOKEN&code=AUTH_CODE
        B->>B: Validate state
        B->>B: Delete state (single-use)
        B->>+O: Exchange code for tokens
        O-->>-B: Access token + ID token
        B->>+O: Get user info
        O-->>-B: User profile data
        B->>B: Create/retrieve user
        B->>B: Generate JWT tokens
        B-->>-C: 200 OK { access_token, refresh_token }
    end
```

### Security Features

| Feature | Implementation | Purpose |
| ------- | -------------- | ------- |
| **CSRF Protection** | Cryptographically secure `state` parameter (32 bytes) | Prevents cross-site request forgery attacks |
| **State TTL** | 10 minutes expiration (`OAUTH_STATE_EXPIRE_SECONDS`) | Prevents replay attacks |
| **Single-use State** | Deleted immediately after validation | Prevents state token reuse |
| **PKCE** | `code_challenge_method=S256` | Prevents authorization code interception |
| **Provider Validation** | State-provider matching | Prevents provider spoofing |
| **Rate Limiting** | 10/min login, 20/min callback | Prevents abuse |

---

## Prerequisites and Dependencies

### System Requirements

- **Python**: 3.13+
- **PostgreSQL**: Running instance (local or Neon)
- **Redis**: For state parameter caching (optional, in-memory fallback available)

### Required Tools

#### For HTTPie Collection

| Tool | Installation | Purpose |
| ---- | ------------ | ------- |
| **HTTPie** | `brew install httpie` (macOS) or `pip install httpie` | HTTP client for API testing |
| **jq** (optional) | `brew install jq` | JSON response formatting |

#### For Postman Collection

| Tool | Installation | Purpose |
| ---- | ------------ | ------- |
| **Postman** | Download from [postman.com](https://www.postman.com/downloads/) | GUI API testing platform |

### Backend Setup

1. **Clone and configure the backend:**

   ```bash
   # Navigate to backend directory
   cd backend

   # Install dependencies
   uv sync

   # Copy environment template
   cp .env.example secrets/.env
   ```

2. **Configure OAuth credentials in `secrets/.env`:**

   ```bash
   # Google OAuth (Required for Google login)
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret

   # OAuth State Configuration
   OAUTH_STATE_EXPIRE_SECONDS=600
   ```

3. **Start the backend server:**

   ```bash
   # Using the run script (recommended)
   ./scripts/run.sh start

   # Or manually with uv
   source .venv/bin/activate
   uv run uvicorn app.main:app --reload --loop uvloop
   ```

4. **Verify the server is running:**

   ```bash
   curl http://localhost:8000/health/live
   ```

---

## Configuration

### Environment Variables

Create or update `secrets/.env` with the following OAuth configuration:

```bash
# =============================================================================
# OAuth Provider Configuration
# =============================================================================

# Google OAuth (Active)
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret

# WeChat OAuth (Pending - uncomment when configured)
# WECHAT_APP_ID=your-wechat-app-id
# WECHAT_APP_SECRET=your-wechat-app-secret

# Apple Sign In (Pending - uncomment when configured)
# APPLE_CLIENT_ID=com.yourcompany.baliblissed.web
# APPLE_TEAM_ID=ABCD123456
# APPLE_KEY_ID=DEF123GHIJ
# APPLE_PRIVATE_KEY_PATH=secrets/apple_auth_key.p8

# =============================================================================
# OAuth Security Configuration
# =============================================================================

# State parameter time-to-live in seconds (default: 600 = 10 minutes)
OAUTH_STATE_EXPIRE_SECONDS=600
```

### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services** > **Credentials**
3. Click **Create Credentials** > **OAuth client ID**
4. Configure the OAuth consent screen if prompted
5. Set application type to **Web application**
6. Add authorized redirect URIs:
   - Development: `http://localhost:8000/auth/callback/google`
   - Production: `https://yourdomain.com/auth/callback/google`
7. Copy the **Client ID** and **Client Secret** to your `secrets/.env`

### Collection Configuration

#### HTTPie Script Variables

Edit the following variables at the top of [`oauth_httpie_collection.sh`](oauth_httpie_collection.sh:11-13):

```bash
# Configuration
BASE_URL="http://localhost:8000"    # Change for production testing
PROVIDER="google"                   # Change to test other providers
```

#### Postman Collection Variables

The Postman collection includes these pre-configured variables:

| Variable | Default Value | Description |
| -------- | ------------- | ----------- |
| `base_url` | `http://localhost:8000` | API base URL |
| `oauth_state` | *(empty)* | State parameter from login redirect |
| `oauth_code` | *(empty)* | Authorization code from provider |
| `access_token` | *(empty)* | JWT access token from callback |

---

## HTTPie Collection Guide

### Quick Start

```bash
# Make the script executable
chmod +x scripts/api/oauth_httpie_collection.sh

# Run the complete collection (displays all test scenarios)
./scripts/api/oauth_httpie_collection.sh
```

### Running Individual Tests

The script is designed as a reference guide. To execute actual requests, uncomment the relevant lines in the script or run commands directly:

#### Test 1: Initiate OAuth Login

```bash
# View the redirect URL and state parameter
http -v GET http://localhost:8000/auth/login/google

# Expected: 302 redirect to Google with state parameter
# HTTP/1.1 302 Found
# Location: https://accounts.google.com/o/oauth2/v2/auth?...
```

#### Test 2: Unconfigured Provider (Error Case)

```bash
http GET http://localhost:8000/auth/login/nonexistent

# Expected: 404 Not Found
# {"detail": "Provider nonexistent not configured"}
```

#### Test 3: OAuth Callback Simulation

```bash
# Replace with actual state and code from a real OAuth flow
http GET http://localhost:8000/auth/callback/google \
  state==YOUR_STATE_FROM_LOGIN \
  code==AUTHORIZATION_CODE_FROM_PROVIDER

# Expected (Success): 200 OK with JWT tokens
# {
#   "access_token": "eyJhbGciOiJIUzI1NiIs...",
#   "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
#   "token_type": "bearer"
# }
```

#### Test 4: Missing State Parameter (Error Case)

```bash
http GET http://localhost:8000/auth/callback/google code==some_code

# Expected: 400 Bad Request
# {"detail": "Missing OAuth state parameter"}
```

#### Test 5: Invalid State (Error Case)

```bash
http GET http://localhost:8000/auth/callback/google \
  state==invalid_state \
  code==some_code

# Expected: 400 Bad Request
# {"detail": "Invalid or expired OAuth state"}
```

### Complete OAuth Flow Test

For a full integration test, follow these steps:

```bash
# Step 1: Get the redirect URL and extract state
http -h GET http://localhost:8000/auth/login/google | grep Location

# Step 2: Open the URL in a browser and complete Google login
# The browser will redirect to:
# http://localhost:8000/auth/callback/google?state=XXX&code=YYY

# Step 3: The callback endpoint automatically exchanges the code
# and returns JWT tokens (check browser or use the URL in httpie)
```

### Multi-Provider Test

```bash
# Test all configured providers
for provider in google wechat apple; do
  echo "Testing: $provider"
  http -h GET http://localhost:8000/auth/login/$provider
done
```

---

## Postman Collection Guide

### Importing the Collection

1. **Open Postman**

2. **Import the collection:**
   - Click **Import** button (top left)
   - Drag and drop [`oauth_postman_collection.json`](oauth_postman_collection.json) or click **Upload Files**
   - Click **Import**

3. **The collection will appear as "BaliBlissed OAuth API"**

### Configuring Environment

1. **Create a new environment:**
   - Click the environment dropdown (top right)
   - Click **+** to create new environment
   - Name it "BaliBlissed Local"

2. **Add variables:**

   | Variable | Initial Value | Current Value |
   | -------- | ------------- | ------------- |
   | `base_url` | `http://localhost:8000` | `http://localhost:8000` |
   | `oauth_state` | | |
   | `oauth_code` | | |
   | `access_token` | | |

3. **Select the environment** from the dropdown before making requests

### Running Requests

#### Folder 1: OAuth Login

**Google OAuth Login:**

1. Select **1. OAuth Login** > **Google OAuth Login**
2. Click **Send**
3. Expected: `302 Found` redirect to Google
4. Check the **Location** header for the authorization URL

**WeChat OAuth Login:**

1. Select **1. OAuth Login** > **WeChat OAuth Login**
2. Click **Send**
3. Expected: `302 Found` or `404 Not Found` (if not configured)

#### Folder 2: OAuth Callback

**Google OAuth Callback:**

1. First, complete a Google login flow to get `state` and `code`
2. Update collection variables:
   - Click **...** on collection > **Edit** > **Variables**
   - Set `oauth_state` and `oauth_code` values
3. Select **2. OAuth Callback** > **Google OAuth Callback**
4. Click **Send**
5. Expected: `200 OK` with JWT tokens
6. Copy `access_token` from response and set it in variables

#### Folder 3: Utilities

**Health Check:**

1. Select **3. Utilities** > **Health Check**
2. Click **Send**
3. Use an admin bearer token when calling the legacy `/health` endpoint
4. Expected: `200 OK` with detailed system health status

**Get Current User:**

1. Ensure `access_token` variable is set from a successful callback
2. Select **3. Utilities** > **Get Current User**
3. Click **Send**
4. Expected: `200 OK` with user profile data

### Using Collection Authorization

The collection is pre-configured with Bearer token authorization:

1. After a successful callback, copy the `access_token` from the response
2. Set it in the collection variables
3. All requests in the collection will automatically include `Authorization: Bearer {{access_token}}`

### Viewing Response Examples

Each request includes saved response examples:

1. Send a request
2. Click **Responses** tab below the response
3. Select from saved examples:
   - **Success - Redirect to Google** (302)
   - **Error - Provider Not Configured** (404)
   - **Success - Tokens** (200)
   - **Error - Missing State** (400)
   - **Error - Invalid State** (400)
   - **Error - Provider Mismatch** (400)

---

## API Endpoints Reference

### 1. Initiate OAuth Login

```http
GET /auth/login/{provider}
```

Initiates the OAuth flow by redirecting to the provider's authorization page.

**Path Parameters:**

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `provider` | string | Yes | OAuth provider: `google`, `wechat`, `apple` |

**Responses:**

| Status | Description | Headers |
| ------ | ----------- | ------- |
| `302` | Redirect to OAuth provider | `Location: https://accounts.google.com/...` |
| `404` | Provider not configured | `Content-Type: application/json` |
| `429` | Rate limit exceeded | `Content-Type: application/json` |

**Example:**

```bash
http GET http://localhost:8000/auth/login/google
```

**Response Headers:**

```http
HTTP/1.1 302 Found
Location: https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id=...&redirect_uri=...&scope=openid+email+profile&state=...
```

---

### 2. OAuth Callback Handler

```http
GET /auth/callback/{provider}?state={state}&code={code}
```

Handles the OAuth provider callback and exchanges the authorization code for JWT tokens.

**Path Parameters:**

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `provider` | string | Yes | OAuth provider name |

**Query Parameters:**

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `state` | string | Yes | CSRF protection state from login |
| `code` | string | Yes | Authorization code from provider |

**Responses:**

| Status | Description | Body |
| ------ | ----------- | ---- |
| `200` | Success - JWT tokens returned | `{"access_token": "...", "refresh_token": "...", "token_type": "bearer"}` |
| `400` | Missing state parameter | `{"detail": "Missing OAuth state parameter"}` |
| `400` | Invalid/expired state | `{"detail": "Invalid or expired OAuth state"}` |
| `400` | Provider mismatch | `{"detail": "OAuth provider mismatch"}` |
| `400` | OAuth authorization failed | `{"detail": "OAuth authorization failed: ..."}` |
| `404` | Provider not found | `{"detail": "Provider not found"}` |
| `429` | Rate limit exceeded | `{"detail": "Too Many Requests"}` |

**Example:**

```bash
http GET http://localhost:8000/auth/callback/google \
  state==abc123... \
  code==4/0AX...
```

**Success Response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

---

### 3. Public Health Check

```http
GET /health/live
```

Returns a lightweight liveness response for public probing.

For detailed operational status, use `GET /health` with an authenticated admin bearer token.

**Responses:**

| Status | Description |
| ------ | ----------- |
| `200` | Application is live |

**Example:**

```bash
http GET http://localhost:8000/health/live
```

---

### 4. Get Current User

```http
GET /auth/me
Authorization: Bearer {access_token}
```

Returns the authenticated user's profile information.

**Headers:**

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `Authorization` | string | Yes | Bearer token from OAuth callback |

**Responses:**

| Status | Description |
| ------ | ----------- |
| `200` | User profile data |
| `401` | Invalid or expired token |

**Example:**

```bash
http GET http://localhost:8000/auth/me \
  "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
| ----- | ----- | -------- |
| `redirect_uri_mismatch` | Redirect URI not registered in OAuth provider console | Add exact callback URL to provider settings: `http://localhost:8000/auth/callback/google` |
| `Provider not configured` | Missing OAuth credentials in environment | Verify `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `secrets/.env` |
| `Invalid or expired OAuth state` | State expired (10 min TTL) or cache issue | Retry the login flow from the beginning |
| `OAuth provider mismatch` | State was generated for different provider | Clear browser cookies and retry |
| `Missing OAuth state parameter` | Callback URL missing state query param | Ensure provider is correctly configured to return state |
| `401 Unauthorized` on `/auth/me` | Invalid or expired access token | Obtain new tokens via OAuth flow |
| Connection refused | Backend not running | Start server with `./scripts/run.sh start` |

### Debug Commands

```bash
# Check if OAuth credentials are loaded
uv run python -c "from app.configs.settings import settings; print('Google Client ID:', bool(settings.GOOGLE_CLIENT_ID))"

# Test OAuth login endpoint
curl -v http://localhost:8000/auth/login/google

# Check backend health
curl http://localhost:8000/health/live | jq

# Check Redis connectivity (for state storage)
redis-cli ping

# View application logs
tail -f logs/app.log
```

### Verifying Configuration

```bash
# 1. Check environment variables are loaded
uv run python -c "
from app.configs.settings import settings
print('Google OAuth configured:', bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET))
print('State TTL:', settings.OAUTH_STATE_EXPIRE_SECONDS, 'seconds')
"

# 2. Test login endpoint returns redirect
http -h GET http://localhost:8000/auth/login/google | head -5

# 3. Verify callback returns expected error for invalid state
http GET http://localhost:8000/auth/callback/google state==invalid code==test
```

### Rate Limiting

OAuth endpoints have rate limiting applied:

| Endpoint | Rate Limit | Scope |
| -------- | ---------- | ----- |
| `/auth/login/{provider}` | 10 requests/minute | Per IP |
| `/auth/callback/{provider}` | 20 requests/minute | Per IP |

If rate limited, wait 1 minute or use a different IP address.

### State Parameter Issues

The state parameter has these constraints:

- **Length**: 32 bytes (URL-safe base64 encoded)
- **TTL**: 600 seconds (10 minutes) by default
- **Single-use**: Deleted immediately after validation
- **Storage**: Redis (or in-memory fallback)

If states are not working:

1. Check Redis is running: `redis-cli ping`
2. Verify admin operational health: `curl -H 'Authorization: Bearer <admin-token>' http://localhost:8000/health | jq '.cache'`
3. Check state TTL configuration: `OAUTH_STATE_EXPIRE_SECONDS`

---

## Additional Resources

- **API Documentation (Swagger)**: <http://localhost:8000/docs>
- **API Documentation (ReDoc)**: <http://localhost:8000/redoc>
- **OAuth Feature Documentation**: [`docs/features/OAUTH.md`](../../docs/features/OAUTH.md)
- **Backend Main Documentation**: [`AGENTS.md`](../../AGENTS.md)

---

## Document Information

- **Created**: 2026-02-24
- **Last Updated**: 2026-02-24
- **Version**: 1.0
- **Authors**: BaliBlissed Development Team
