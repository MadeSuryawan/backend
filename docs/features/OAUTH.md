# OAuth Authentication Documentation

Complete guide for OAuth authentication in BaliBlissed Backend.

## Table of Contents

1. [Overview](#overview)
2. [Implemented Features](#implemented-features)
3. [Security Features](#security-features)
4. [Configuration](#configuration)
5. [API Endpoints](#api-endpoints)
6. [Testing](#testing)
7. [Provider Setup Guides](#provider-setup-guides)
8. [Deliverables Summary](#deliverables-summary)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The BaliBlissed Backend supports OAuth 2.0 authentication for seamless user login through third-party providers. Currently, the system is architected to support multiple providers with production-ready security implementations.

### Supported Providers

| Provider | Status | Notes |
| -------- | -------- | -------- |
| **Google** | ✅ Active | Fully configured and tested |
| **WeChat** | ⚠️ Pending | Architecture ready, credentials not configured |
| **Apple** | ⚠️ Pending | Architecture ready, credentials not configured |

---

## Implemented Features

### Core OAuth Flow

1. **Login Initiation** (`/auth/login/{provider}`)
   - Redirects user to OAuth provider
   - Generates CSRF protection state
   - Enables PKCE for enhanced security

2. **Callback Handler** (`/auth/callback/{provider}`)
   - Validates state parameter
   - Exchanges code for access token
   - Creates/retrieves user
   - Returns JWT tokens

### Security Implementations

| Feature | Implementation | Purpose |
| -------- | -------- | -------- |
| **CSRF Protection** | State parameter validation | Prevents cross-site request forgery |
| **State TTL** | 10 minutes expiration | Prevents replay attacks |
| **Single-use State** | Deleted after validation | Prevents state replay |
| **PKCE** | `code_challenge_method=S256` | Prevents authorization code interception |
| **Provider Validation** | State-provider matching | Prevents provider spoofing |
| **Security Logging** | Failed attempt logging | Attack monitoring & forensics |

---

## Security Features

### CSRF Protection via State Parameter

```plain text
1. User clicks "Login with Google"
2. Backend generates: state = secrets.token_urlsafe(32)
3. Stores in cache: oauth_state:{state} → {provider, ip}
4. Redirects to Google with state parameter
5. Google redirects back with same state
6. Backend validates state exists and matches provider
7. State deleted immediately (single-use)
8. Tokens issued on successful validation
```

### PKCE (Proof Key for Code Exchange)

Both Google and WeChat configurations include PKCE:

```python
client_kwargs={
    "scope": "openid email profile",
    "code_challenge_method": "S256",  # Enable PKCE
}
```

---

## Configuration

### Environment Variables

Add to `secrets/.env`:

```bash
# Google OAuth (Active)
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret

# WeChat OAuth (Pending Setup)
WECHAT_APP_ID=your-wechat-app-id
WECHAT_APP_SECRET=your-wechat-app-secret

# Apple OAuth (Pending Setup)
APPLE_CLIENT_ID=your-apple-services-id
APPLE_TEAM_ID=your-team-id
APPLE_KEY_ID=your-key-id
APPLE_PRIVATE_KEY_PATH=secrets/apple_auth_key.p8

# OAuth State Configuration
OAUTH_STATE_EXPIRE_SECONDS=600  # 10 minutes TTL
```

### Settings

The `OAUTH_STATE_EXPIRE_SECONDS` setting controls how long the state parameter remains valid (default: 600 seconds / 10 minutes).

---

## API Endpoints

### 1. Initiate OAuth Login

```http
GET /auth/login/{provider}
```

**Parameters:**

| Name        | Type        | Required    | Description                                  |
| ----------- | ----------- | ----------- | -------------------------------------------- |
| `provider`  | string      | Yes         | OAuth provider (`google`, `wechat`)          |

**Responses:**

| Status      | Description                                  |
| ----------- | -------------------------------------------- |
| `307`       | Temporary redirect to OAuth provider         |
| `404`       | Provider not configured                      |

**Example:**

```bash
curl -v http://localhost:8000/auth/login/google
```

**Response Headers:**

```http
HTTP/1.1 302 Found
Location: https://accounts.google.com/o/oauth2/v2/auth?...
Set-Cookie: session=...
```

---

### 2. OAuth Callback

```http
GET /auth/callback/{provider}?state={state}&code={code}
```

**Parameters:**

| Name        | Type        | Required    | Description                                  |
| ----------- | ----------- | ----------- | -------------------------------------------- |
| `provider`  | string      | Yes         | OAuth provider                               |
| `state`     | string      | Yes         | CSRF protection state                        |
| `code`      | string      | Yes         | Authorization code from provider             |

**Responses:**

**Success (200):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Errors:**

| Status      | Error                                    | Description                                  |
| ----------- | ---------------------------------------- | -------------------------------------------- |
| `400`       | Missing OAuth state parameter            | State not provided                           |
| `400`       | Invalid or expired OAuth state           | State not found or expired                   |
| `400`       | OAuth provider mismatch                  | State was for different provider             |
| `400`       | OAuth authorization failed               | Token exchange error                         |
| `404`       | Provider not found                       | Unconfigured provider                        |

---

## Testing

### Running OAuth Tests

```bash
# Run all OAuth tests
uv run pytest tests/auth/test_oauth.py -v

# Run with coverage
uv run pytest tests/auth/test_oauth.py --cov=app.routes.auth
```

### Test Coverage

| Test Category     | Count | Description                                          |
| ----------------- | ----- | ---------------------------------------------------- |
| Login Tests       | 2     | Provider configuration, state generation             |
| Callback Tests    | 3     | Missing state, invalid state, provider not found     |
| CSRF Protection   | 2     | Single-use state, TTL expiration                     |
| Error Handling    | 1     | Provider mismatch                                    |
| Provider Support  | 4     | Multi-provider URL tests                             |
| Security Features | 2     | State info, CSRF enforcement                         |

## **Total: 14 test cases**

### Testing Tools

#### HTTPie Collection

Location: `docs/api/oauth_httpie_collection.sh`

```bash
# Make executable
chmod +x docs/api/oauth_httpie_collection.sh

# Run all examples
./docs/api/oauth_httpie_collection.sh

# Individual tests
http GET http://localhost:8000/auth/login/google
http GET http://localhost:8000/auth/callback/google?state=xxx&code=yyy
```

#### Postman Collection

Location: `docs/api/oauth_postman_collection.json`

1. Open Postman
2. File → Import
3. Select `docs/api/oauth_postman_collection.json`
4. Update `base_url` environment variable

---

## Provider Setup Guides

### Google OAuth ✅ Active

**Prerequisites:**

- Google Cloud account
- OAuth 2.0 credentials

**Setup Steps:**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. APIs & Services → Credentials → Create Credentials → OAuth client ID
3. Configure OAuth consent screen
4. Application type: Web application
5. Add authorized redirect URIs:
   - `http://localhost:8000/auth/callback/google` (dev)
   - `https://yourdomain.com/auth/callback/google` (prod)
6. Copy Client ID and Client Secret to `secrets/.env`

**Status:** Currently configured and operational.

---

### WeChat OAuth ⚠️ Pending

**Status:** Architecture implemented, credentials not configured.

**Prerequisites:**

- WeChat Open Platform account
- Business entity verification (typically required)
- Domain verification (no localhost support)

**Setup Steps:**

1. Register at [WeChat Open Platform](https://open.weixin.qq.com/)
2. Create Web Application
3. Configure authorized domain (domain only, not full URL)
4. Obtain AppID and AppSecret
5. For development, use **ngrok** (WeChat doesn't support localhost)

**Configuration Required:**

```bash
WECHAT_APP_ID=wx1234567890abcdef
WECHAT_APP_SECRET=your-app-secret
```

**Notes:**

- WeChat requires HTTPS
- QR code login flow
- More complex setup than Google
- Consider skipping if no immediate Chinese user base

---

### Apple Sign In ⚠️ Pending

**Status:** Architecture implemented, credentials not configured.

**Prerequisites:**

- Apple Developer account ($99/year)
- Domain ownership verification
- HTTPS endpoints only

**Setup Steps:**

1. Apple Developer Portal → Certificates, Identifiers & Profiles
2. Create App ID with "Sign in with Apple" capability
3. Create Services ID for web
4. Configure authorized domains and return URLs
5. Create private key (download .p8 file)
6. Store key at `secrets/apple_auth_key.p8`

**Configuration Required:**

```bash
APPLE_CLIENT_ID=com.yourcompany.baliblissed.web
APPLE_TEAM_ID=ABCD123456
APPLE_KEY_ID=DEF123GHIJ
APPLE_PRIVATE_KEY_PATH=secrets/apple_auth_key.p8
```

**Notes:**

- Apple requires HTTPS (use ngrok for dev)
- Private key can only be downloaded once
- Mandatory if you have an iOS app with other social logins

---

## Deliverables Summary

### 1. OAuth Test Suite

**File:** `tests/auth/test_oauth.py`

**Features:**

- 14 comprehensive test cases
- CSRF protection validation
- State parameter lifecycle testing
- Error scenario coverage
- Multi-provider support tests

**Usage:**

```bash
uv run pytest tests/auth/test_oauth.py -v
```

### 2. HTTPie Collection

**File:** `docs/api/oauth_httpie_collection.sh`

**Contents:**

- OAuth login initiation
- Callback simulation
- Error case testing
- Complete flow walkthrough
- Multi-provider examples

### 3. Postman Collection

**File:** `docs/api/oauth_postman_collection.json`

**Contents:**

- Import-ready collection
- Environment variables
- Request/response examples
- Error response documentation

### 4. Enhanced Swagger Documentation

**File:** `app/routes/auth.py`

**Features:**

- Detailed endpoint descriptions
- Security feature documentation
- Request/response examples
- Error scenario documentation
- Tagged under "🔐 OAuth"

**Access:**

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 5. Code Implementation

**Files Modified:**

- `app/routes/auth.py` - OAuth endpoints with CSRF protection
- `app/services/auth.py` - OAuth user handling
- `app/repositories/user.py` - User creation with verification
- `app/errors/auth.py` - OAuth error classes
- `app/configs/settings.py` - OAuth configuration

---

## Troubleshooting

### Common Issues

| Issue.                           | Cause.                                  | Solution.                                 |
| ------------------------------   | --------------------------------------- | ----------------------------------------- |
| `redirect_uri_mismatch`          | Redirect URI not registered             | Add exact URI to OAuth provider console   |
| `Provider not configured`        | Missing environment variables           | Check `secrets/.env` for credentials      |
| `Invalid or expired OAuth state` | State expired or cache issue            | State expires after 10 minutes, try again |
| `OAuth provider mismatch`        | State was for different provider        | Clear browser cookies, retry login        |
| `Missing OAuth state parameter`  | Callback missing state                  | Provider didn't return state, check config|

### Debug Commands

```bash
# Check if credentials are loaded
uv run python -c "from app.configs import settings; print('Google:', bool(settings.GOOGLE_CLIENT_ID))"

# Test OAuth endpoint
curl -v http://localhost:8000/auth/login/google

# Check cache health
curl http://localhost:8000/health | jq '.cache'
```

---

## Security Checklist

- [x] CSRF protection via state parameter
- [x] State is single-use (deleted after validation)
- [x] State has TTL (10 minutes)
- [x] PKCE enabled for all providers
- [x] Provider validation on callback
- [x] Security logging for failures
- [x] OAuth errors don't expose sensitive info
- [x] HTTPS required for production
- [x] Rate limiting on OAuth endpoints (10/minute for login, 20/minute for callback)

---

## Future Enhancements

1. **Additional Providers:**
   - Facebook Login
   - Twitter/X OAuth
   - GitHub OAuth
   - LinkedIn OAuth

2. **Features:**
   - Account linking (connect multiple providers)
   - Provider disconnection
   - OAuth-only user management
   - Custom OAuth provider support

3. **Monitoring:**
   - OAuth success/failure metrics
   - Provider usage statistics
   - Security event alerting

---

## References

- [OAuth 2.0 Specification](https://oauth.net/2/)
- [PKCE Specification](https://oauth.net/2/pkce/)
- [Google OAuth 2.0 Guide](https://developers.google.com/identity/protocols/oauth2)
- [Authlib Documentation](https://docs.authlib.org/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)

---

## Document Information

- **Created:** 2026-02-10
- **Last Updated:** 2026-02-10
- **Version:** 1.0
- **Status:** Active
