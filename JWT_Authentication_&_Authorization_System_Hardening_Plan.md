# JWT Authentication & Authorization System Hardening Plan

## Problem Statement

The current JWT authentication system has significant gaps compared to IMPROVEMENTS.md requirements and security best practices. While basic login/registration exists, critical features like refresh tokens, token revocation, email verification, and proper RBAC are missing, creating security vulnerabilities and poor UX.

## Current State Analysis

### Implemented Features

* **Token Manager** (`app/managers/token_manager.py`): Basic `create_access_token()` and `decode_access_token()` using `python-jose` with HS256
* **Auth Service** (`app/services/auth.py`): Username/password authentication, OAuth user creation
* **Auth Routes** (`app/routes/auth.py`): Login, register, OAuth flows, `/me` endpoint
* **Dependencies** (`app/dependencies/dependencies.py`): `get_current_user()` checking `is_active`
* **Password Hashing** (`app/managers/password_manager.py`): Argon2id with configurable security levels
* **Settings** (`app/configs/settings.py`): `SECRET_KEY`, `ALGORITHM=HS256`, `ACCESS_TOKEN_EXPIRE_MINUTES=30`

### Critical Gaps Identified

1. **No refresh token system** - Users must re-login after 30 minutes
2. **No token revocation/blacklist** - Compromised tokens cannot be invalidated
3. **Missing endpoints**: `/auth/refresh`, `/auth/logout`, `/auth/verify-email`, `/auth/forgot-password`, `/auth/reset-password`
4. **No `require_verified_user()` dependency** - `is_verified` flag never enforced
5. **Localhost-only admin check** - Bypassable via proxies (`host(request) not in ("127.0.0.1", "::1", "localhost")`)
6. **Minimal JWT claims** - Only `sub` (username) and `exp`; missing `jti`, `iat`, `iss`, `aud`, `type`, `user_id`

## Security Vulnerabilities

### Critical

* **CVE-like: Token cannot be revoked** - If token is stolen, attacker has access until expiry
* **Default SECRET_KEY in code** (`settings.py:180`) - Should be environment-only with no default
* **No account lockout** - Brute-force attacks possible despite rate limiting

### High

* **No user UUID in token** - Requires DB lookup by username on every request
* **Admin routes use IP check** - Easily bypassed with `X-Forwarded-For` spoofing
* **OAuth state not validated** - Potential CSRF in OAuth flows

### Medium (RFC 7519 / OWASP)

* Missing `iss` (issuer) claim validation
* Missing `aud` (audience) claim validation  
* Missing `jti` (JWT ID) for uniqueness tracking
* Missing `iat` (issued at) timestamp
* No token type differentiation (access vs refresh)

## Implementation Plan

### Phase 1: Enhanced JWT Infrastructure

**Files to modify:**

* `app/managers/token_manager.py`
* `app/schemas/auth.py`
* `app/configs/settings.py`
**Changes:**

1. Add settings: `REFRESH_TOKEN_EXPIRE_DAYS=7`, `JWT_ISSUER`, `JWT_AUDIENCE`
2. Enhance `create_access_token()` with claims: `jti`, `iat`, `iss`, `aud`, `type=access`, `user_id`
3. Create `create_refresh_token()` with claims: `jti`, `iat`, `iss`, `aud`, `type=refresh`, `user_id`
4. Update `decode_access_token()` to validate `iss`, `aud`, and `type`
5. Update `TokenData` schema to include `user_id`, `jti`, `token_type`

### Phase 2: Redis Token Blacklist

**Files to create:**

* `app/managers/token_blacklist.py`
**Files to modify:**
* `app/managers/token_manager.py`
* `app/dependencies/dependencies.py`
**Changes:**

1. Create `TokenBlacklist` class using Redis with TTL matching token expiration
2. Methods: `add_to_blacklist(jti, exp)`, `is_blacklisted(jti)`, `cleanup_expired()`
3. Integrate blacklist check into `decode_access_token()`
4. Update `get_current_user()` to check blacklist

### Phase 3: New Authentication Endpoints

**Files to modify:**

* `app/routes/auth.py`
* `app/services/auth.py`
**New endpoints:**

1. `POST /auth/refresh` - Exchange refresh token for new access token (rotate refresh token)
2. `POST /auth/logout` - Add tokens to blacklist
3. `POST /auth/verify-email` - Verify email with token
4. `POST /auth/forgot-password` - Send password reset email
5. `POST /auth/reset-password` - Reset password with token
**Service methods to add:**

* `refresh_tokens(refresh_token)` with refresh token rotation
* `logout_user(access_token, refresh_token)`
* `send_verification_email(user)`
* `verify_email(token)`
* `send_password_reset(email)`
* `reset_password(token, new_password)`

### Phase 4: Enhanced Dependencies & Enforcement

**Files to create:**

* `app/auth/permissions.py`
**Files to modify:**
* `app/dependencies/dependencies.py`
* `app/routes/user.py`
* `app/routes/blog.py`
**Changes:**

1. Create `require_verified_user()` dependency
2. Create `require_active_user()` dependency (existing logic, extracted)
3. Update routes to use appropriate dependencies
4. Add ownership verification for blog update/delete

### Phase 5: Account Security Hardening

**Files to create:**

* `app/managers/login_attempt_tracker.py`
**Files to modify:**
* `app/services/auth.py`
* `app/routes/auth.py`
* `app/configs/settings.py`
**Changes:**

1. Track failed login attempts per user/IP in Redis
2. Implement account lockout after N failed attempts (configurable)
3. Add settings: `MAX_LOGIN_ATTEMPTS=5`, `LOCKOUT_DURATION_MINUTES=15`
4. Add exponential backoff for repeated failures
5. Remove default `SECRET_KEY` value - require environment variable

## Prioritized Action Items

### P0 - Immediate (Security Critical)

1. Remove default `SECRET_KEY` - require env var
2. Implement refresh token system
3. Implement token blacklist for logout/revocation
4. Add `jti` claim for token tracking

### P1 - Short-term (Production Readiness)

1. Add `/auth/refresh` endpoint with token rotation
2. Add `/auth/logout` endpoint
3. Implement account lockout mechanism
4. Add `user_id` to token claims for efficient lookups

### P2 - Medium-term (IMPROVEMENTS.md Compliance)

1. Add email verification flow (`/auth/verify-email`)
2. Add password reset flow (`/auth/forgot-password`, `/auth/reset-password`)
3. Create `require_verified_user()` dependency
4. Update protected routes to enforce verification

### P3 - Long-term (Best Practices)

1. Add `iss`, `aud` claim validation
2. Replace localhost admin checks with proper RBAC (ties into P0 item #3 from IMPROVEMENTS.md)
3. Add CSRF protection for OAuth state parameter
4. Implement token binding to prevent token theft across devices
