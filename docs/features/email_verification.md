# Email Verification Feature

## Overview

This feature enforces email verification for new user sign-ups. It utilizes the `is_verified` column in the `UserDB` model and follows security best practices with time-limited JWT verification tokens.

## Status: ✅ FULLY IMPLEMENTED

The email verification flow is fully integrated with the Gmail API via `EmailClient`. Tokens are generated, rate-limited, and dispatched in a professional HTML format.

---

## Table of Contents

1. [Workflow](#workflow)
2. [API Endpoints](#api-endpoints)
3. [Security Measures](#security-measures)
4. [Testing](#testing)

---

## Workflow

### 1. User Registration (`/auth/register`)

- **User Action**: Submits registration form (username, email, password).
- **System Action**:
    1. Creates user account with `is_verified=False`.
    2. Generates a secured, time-limited verification token.
    3. Records the "send" action for rate limiting.
    4. Sends verification email with professional HTML template.
- **Response**: 201 Created. User receives access token but is restricted from verified-only endpoints.

### 2. Email Verification (`/auth/verify-email`)

- **User Action**: Extracts token from email verification link and calls API.
- **System Action**:
    1. Decodes token and validates signature, expiration, and type.
    2. Checks if token has already been used (prevents replay attacks).
    3. Verifies that the token's email claim matches the user's current email.
    4. Updates user's `is_verified` status to `True`.
    5. Marks token as used in Redis (24-hour TTL).
- **Response**: 200 OK on success, 401 on invalid/expired/used token.

### 3. Email Change Re-verification (`/users/update/{user_id}`)

- **User Action**: Updates their email address.
- **System Action**:
    1. Detects email change in update request.
    2. Updates email in database.
    3. Sets `is_verified=False` (requires re-verification).
    4. Generates new verification token for new email.
    5. Sends verification email to the **new** address.
- **Response**: 200 OK with updated user (now unverified).

**Security Note**: This prevents account hijacking via email change. A user must verify their new email before accessing verified-only features.

### 4. Resend Verification (`/auth/resend-verification`)

- **User Action**: Requests a new verification email.
- **System Action**:
    1. Checks rate limits (prevents spam).
    2. Generates new token.
    3. Sends new verification email.
- **Response**: 200 OK (Always returns success to prevent email enumeration).

---

## API Endpoints

### 1. Register User

**POST** `/auth/register`

Registers a new user and triggers the verification flow.

```bash
curl -X 'POST' \
  'http://localhost:8000/auth/register' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "userName": "johndoe",
    "firstName": "John",
    "lastName": "Doe",
    "email": "johndoe@example.com",
    "password": "Password123",
    "country": "USA"
  }'
```

**Response**: 201 Created with user data. Check your email for the verification link.

### 2. Verify Email

**POST** `/auth/verify-email`

Verifies the user's email address using the token from the verification email.

**Request:**

```bash
curl -X 'POST' \
  'http://localhost:8000/auth/verify-email' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }'
```

**Success Response:**

```json
{
  "message": "Email verified successfully",
  "success": true
}
```

**Error Responses:**

| Status | Error | Description |
|--------|-------|-------------|
| 401 | Invalid token | Token is malformed, expired, or signature invalid |
| 401 | Token already used | Token was previously used for verification |
| 401 | Email mismatch | User's email changed since token was issued |

### 3. Update Email (Triggers Re-verification)

**PUT** `/users/update/{user_id}`

Updates user information. If the email is changed, the user will be marked as unverified and a new verification email will be sent.

```bash
curl -X 'PUT' \
  'http://localhost:8000/users/update/123e4567-e89b-12d3-a456-426614174000' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -d '{
    "email": "newemail@example.com"
  }'
```

**Response:**

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "username": "johndoe",
  "email": "newemail@example.com",
  "isVerified": false,
  "isActive": true
}
```

**Behavior:**

- Email is updated immediately
- `isVerified` is set to `false`
- Verification email is sent to the **new** address
- User must re-verify before accessing verified-only features

### 4. Resend Verification

**POST** `/auth/resend-verification`

Requests a new verification email.

```bash
curl -X 'POST' \
  'http://localhost:8000/auth/resend-verification' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "johndoe@example.com"
  }'
```

**Response:**

```json
{
  "message": "If your email is registered and unverified, a new verification email has been sent",
  "success": true
}
```

---

## Security Measures

### Token Security

- **Type Separation**: Verification tokens have a distinct `type: verification` claim, making them unusable as access tokens.
- **Email Binding**: The token contains the `email` address. If a user changes their email address after requesting a verification email but before clicking the link, the token becomes invalid.
- **One-Time Use**: Tokens are tracked in Redis after first use. Subsequent attempts with the same token are rejected.
- **Expiration**: Short-lived tokens (configurable, default 24 hours via `VERIFICATION_TOKEN_EXPIRE_HOURS`).

### Rate Limiting

- **Redis-backed**: Uses Redis to track verification requests per user.
- **Limits**: Configured in settings (`VERIFICATION_RESEND_LIMIT`, default 3 per 24 hours).

### Access Control

- **`VerifiedUserDep`**: A dependency `get_verified_user` exists to protect routes that require a verified email.
- **Admin Access**: Admin user creation (`/users/create`) is restricted to admins and does not trigger the public verification flow.

---

## Testing

### Running Test Suite

```bash
# Run all auth tests
uv run pytest tests/auth/ -v

# Run specific verification flow tests
uv run pytest tests/auth/test_registration_flow.py -v
```

### Manual Testing with cURL

#### Complete Flow Test

**Step 1: Register a new user**

```bash
curl -X 'POST' \
  'http://localhost:8000/auth/register' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "userName": "testuser123",
    "firstName": "Test",
    "lastName": "User",
    "email": "your-email@gmail.com",
    "password": "Password123",
    "country": "USA"
  }'
```

**Step 2: Check email for verification link**

The verification email contains a link like:
```
http://localhost:3000/verify-email?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Step 3: Extract and verify the token**

Copy the token value from the email URL and verify:

```bash
curl -X 'POST' \
  'http://localhost:8000/auth/verify-email' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "token": "PASTE_TOKEN_HERE"
  }'
```

**Step 4: Verify token cannot be reused**

Try the same request again - it should fail:

```bash
curl -X 'POST' \
  'http://localhost:8000/auth/verify-email' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "token": "SAME_TOKEN_AS_BEFORE"
  }'

# Expected response:
# {"detail": "Verification token has already been used"}
```

#### Test Email Change (Re-verification)

```bash
# Step 1: Login to get access token
curl -X 'POST' \
  'http://localhost:8000/auth/login' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=testuser123&password=Password123'

# Step 2: Change email (requires authentication)
curl -X 'PUT' \
  'http://localhost:8000/users/update/USER_ID_HERE' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -d '{
    "email": "new-email@example.com"
  }'

# Response: isVerified is now false
# {
#   "id": "...",
#   "email": "new-email@example.com",
#   "isVerified": false
# }

# Step 3: Check new email and verify
curl -X 'POST' \
  'http://localhost:8000/auth/verify-email' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "token": "TOKEN_FROM_NEW_EMAIL"
  }'
```

#### Test Resend Verification

```bash
# Request new verification email
curl -X 'POST' \
  'http://localhost:8000/auth/resend-verification' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "your-email@gmail.com"
  }'

# Check email and verify with new token
curl -X 'POST' \
  'http://localhost:8000/auth/verify-email' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "token": "NEW_TOKEN_FROM_EMAIL"
  }'
```

### Expected Behaviors

| Scenario | Expected Result |
|----------|-----------------|
| First verification attempt | ✅ `200 OK` - "Email verified successfully" |
| Second attempt with same token | ❌ `401 Unauthorized` - "Token has already been used" |
| Invalid token | ❌ `401 Unauthorized` - "Invalid or expired verification token" |
| Expired token (>24h) | ❌ `401 Unauthorized` - "Invalid or expired verification token" |
| Resend verification | ✅ `200 OK` - New email sent (rate limited) |
| Verify already verified user | ✅ `200 OK` - Still returns success |
| Email change | ✅ `200 OK` - User updated, `isVerified: false`, verification email sent |
| Old token after email change | ❌ `401 Unauthorized` - "Email mismatch" |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VERIFICATION_TOKEN_EXPIRE_HOURS` | 24 | Token validity period |
| `VERIFICATION_RESEND_LIMIT` | 3 | Max resend attempts per 24h |
| `FRONTEND_URL` | http://localhost:3000 | Base URL for verification links in emails |

### Redis Key Format

Used tokens are tracked in Redis with the following key pattern:

```
verification_token:used:<jti> → "1" (TTL: 24 hours)
```

Example:
```
verification_token:used:85683e20-ee7e-42de-9d28-7be6e6dec32a
```

---

## Frontend Integration Guide

When building the frontend, implement a `/verify-email` page that:

1. Extracts the `token` query parameter from the URL
2. Calls `POST /auth/verify-email` with the token
3. Displays success/error messages based on the response

Example URL handling:
```javascript
// React/Vue/Angular example
const urlParams = new URLSearchParams(window.location.search);
const token = urlParams.get('token');

// POST to /auth/verify-email with the token
```

---

## Completed Implementation

- [x] **Email Service Integration**: Integrated `EmailClient` into `register_user` and `resend_verification`
- [x] **Token Single-Use**: Tokens are tracked in Redis and cannot be reused
- [x] **Rate Limiting**: Prevents verification email spam
- [x] **Security**: Email binding, type separation, expiration
- [x] **Email Change Re-verification**: Users must re-verify when changing email
- [ ] **Frontend Landing Page**: Build `/verify-email` page (frontend team)
