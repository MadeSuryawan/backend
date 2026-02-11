# User-Friendly Error Messages

This document outlines the user-friendly error messages implemented throughout the BaliBlissed backend API. All error messages are designed to be:

- **Clear and easy to understand** - No technical jargon
- **Action-oriented** - Tell users what to do next
- **Polite and friendly** - Uses positive, helpful tone
- **Context-aware** - Explains why something happened

---

## 🔐 Authentication Errors

### Login & Credentials

| Error.                 | Status Code | Message                                                                                                                                                                                |
| ---------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Invalid Credentials    | 401         | "Oops! The email/username or password you entered doesn't match our records. Please try again."                                                                                        |
| Account Locked         | 429         | "Your account is temporarily locked for security reasons after multiple failed login attempts. Please try again in {minutes} minute(s) or reset your password if you've forgotten it." |
| Token Expired          | 401         | "Your session has expired for security reasons. Please sign in again to continue."                                                                                                     |
| Invalid Token          | 401         | "Your session has expired or is no longer valid. Please sign in again to continue."                                                                                                    |
| Token Revoked          | 401         | "Your session has been signed out. Please sign in again to continue."                                                                                                                  |
| Invalid Refresh Token  | 401         | "Your session has expired. Please sign in again to continue."                                                                                                                          |

### Admin & Permissions

| Error                    | Status Code | Message                                                                                                   |
| ------------------------ | ----------- | --------------------------------------------------------------------------------------------------------- |
| Insufficient Permissions | 403         | "Sorry, you don't have permission to access this feature. This area is reserved for {role} users only."   |
| Admin Access Required    | 403         | "Sorry, you don't have permission to access this feature. This area is reserved for admin users only."    |
| Not Owner or Admin       | 403         | "Sorry, you can only manage your own {resource}. Please contact an admin if you need assistance."         |

### Account Status

| Error                         | Status Code | Message                                                                                                                                     |
| ----------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Email Not Verified            | 403         | "Your email address hasn't been verified yet. Please check your inbox for a verification email or request a new one to unlock your account."|
| Account Deactivated           | 401         | "This account has been deactivated. Please contact support if you believe this is an error."                                                |
| User Not Found                | 404         | "We couldn't find a user with this information. Please check your details and try again."                                                   |
| Credentials Validation Failed | 401         | "We couldn't verify your credentials. Please sign in again to continue."                                                                    |

### Verification & Reset Tokens

| Error                       | Status Code | Message                                                                                                                                                                                       |
| --------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------    |
| Email Verification Failed   | 401         | "This verification link is invalid or has expired. Please request a new verification email to try again."                                                                                     |
| Verification Token Used     | 401         | "This verification link has already been used. Your email may already be verified - try signing in. If you're still having trouble, request a new verification email."                        |
| Password Reset Failed       | 401         | "This password reset link is invalid or has expired. For your security, reset links expire after a limited time. Please request a new password reset email."                                  |
| Reset Token Used            | 401         | "This password reset link has already been used. For security reasons, each link can only be used once. Please request a new password reset email if you still need to reset your password."  |
| Password Change Failed      | 400         | "We couldn't change your password. Please make sure your current password is correct and that your new password meets our security requirements."                                             |

### OAuth

| Error                   | Status Code | Message                                                                                                                                                               |
| ----------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OAuth Failed            | 400         | "We couldn't complete your sign-in with the selected provider. Please try again or use a different sign-in method."                                                   |
| OAuth State Error       | 400         | "For your security, this sign-in attempt couldn't be verified. The session may have expired - please try signing in again."                                           |
| Provider Not Configured | 404         | "This sign-in method is not available right now. Please try a different sign-in option."                                                                              |

---

## 💾 Database Errors

| Error                    | Status Code | Message                                                                                |
| -----------------------  | ----------- | -------------------------------------------------------------------------------------- |
| Database Connection      | 500         | "We're having trouble connecting to our servers. Please try again in a moment."        |
| Database Configuration   | 500         | "We're experiencing technical difficulties. Please try again later."                   |
| Database Initialization  | 500         | "We're experiencing technical difficulties. Please try again later."                   |
| Duplicate Entry          | 409         | "This information is already in use. Please try something different."                  |
| Unique Violation (Parsed)| 409         | "An account with this {field} '{value}' already exists. Please sign in instead."       |
| Record Not Found         | 404         | "We couldn't find what you're looking for. It may have been removed or doesn't exist." |
| Transaction Failed       | 500         | "Something went wrong while processing your request. Please try again."                |

---

## 📧 Email Service Errors

| Error               | Status Code | Message                                                                                    |
| ------------------- | ----------- | ------------------------------------------------------------------------------------------ |
| Email Service       | 500         | "We're having trouble sending emails right now. Please try again later."                   |
| Email Configuration | 503         | "Email services are temporarily unavailable. Please try again later."                      |
| Email Authentication| 401         | "We're having trouble sending emails right now. Please try again later."                   |
| Email Sending       | 502         | "We couldn't send the email. Please try again or contact support if the problem persists." |
| Email Network       | 503         | "We're experiencing connection issues. Please check your internet and try again."          |

---

## 🤖 AI Service Errors

| Error                   | Status Code | Message                                                                                                     |
| ----------------------- | ----------- | ----------------------------------------------------------------------------------------------------------- |
| AI Service              | 500         | "We're having trouble with our AI service. Please try again in a moment."                                   |
| AI Authentication       | 401         | "Our AI service is temporarily unavailable. Please try again later."                                        |
| AI Quota Exceeded       | 429         | "We've reached our AI service limit. Please try again in a few moments."                                    |
| AI Network              | 503         | "We're having trouble connecting to our AI service. Please try again."                                      |
| AI Response             | 502         | "We received an unexpected response from our AI service. Please try again."                                 |
| AI Content Generation   | 502         | "We couldn't generate the content you requested. Please try again or rephrase your request."                |
| AI Client               | 502         | "We're having trouble with our AI service. Please try again in a moment."                                   |
| Itinerary Generation    | 502         | "We couldn't create your itinerary right now. Please try again or contact us for personalized assistance."  |
| Query Processing        | 502         | "We couldn't process your question. Please try rephrasing it or ask something else."                        |
| Contact Analysis        | 502         | "We couldn't analyze your message. Please try again or submit your inquiry directly."                       |

---

## 📤 Upload/File Errors

| Error                  | Status Code | Message                                                                                                       |
| ---------------------- | ----------- | ------------------------------------------------------------------------------------------------------------- |
| Upload Failed          | 500         | "We couldn't upload your file. Please try again."                                                             |
| Image Too Large        | 413         | "Your image is too large. Please use an image smaller than {max_size_mb}MB."                                  |
| Unsupported Image Type | 415         | "This image format isn't supported. Please use JPEG, PNG, or WebP images."                                    |
| Invalid Image          | 400         | "This file doesn't appear to be a valid image. Please try a different file."                                  |
| Image Processing       | 500         | "We couldn't process your image. Please try a different file or try again later."                             |
| Storage Error          | 500         | "We couldn't save your file. Please try again later."                                                         |
| No Profile Picture     | 400         | "You don't have a profile picture to delete."                                                                 |
| Media Limit Exceeded   | 400         | "You've reached the maximum limit of {max_count} {media_type} files. Please remove some before adding more."  |
| Video Too Large        | 413         | "Your video is too large. Please use a video smaller than {max_size_mb}MB."                                   |
| Unsupported Video Type | 415         | "This video format isn't supported. Please use MP4, WebM, or QuickTime videos."                               |

---

## 🔒 Password/Security Errors

| Error            | Status Code | Message                                                                             |
| ---------------- |-------------| ----------------------------------------------------------------------------------- |
| Password Hashing | 417         | "We couldn't process your password. Please try again or use a different password."  |
| Password Rehash  | 417         | "We encountered an issue with your password. Please try signing in again."          |

---

## ✅ Validation Errors

| Error             | Status Code | Message                                                                                                     |
| ----------------- | ----------- | ----------------------------------------------------------------------------------------------------------- |
| Validation Failed | 422         | "Some of the information you provided doesn't look quite right. Please check your entries and try again."   |

---

## 🔗 Specific Endpoint Error Examples

### Authentication Endpoints

| Endpoint                        | Status | Error Example                                                                                                        |
| ------------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------- |
| `POST /auth/login`              | 401    | "Oops! The email/username or password you entered doesn't match our records. Please try again."                      |
| `POST /auth/login`              | 429    | "Your account is temporarily locked for security reasons after multiple failed login attempts..."                    |
| `POST /auth/register`           | 400    | "An account with this username or email already exists. Please sign in instead or use a different email."            |
| `POST /auth/verify-email`       | 400    | "This verification link is invalid or has expired. Please request a new verification email to try again."            |
| `POST /auth/verify-email`       | 401    | "This verification link has already been used. Your email may already be verified - try signing in."                 |
| `POST /auth/reset-password`     | 400    | "This password reset link is invalid or has expired. Please request a new password reset email."                     |
| `POST /auth/reset-password`     | 401    | "This password reset link has already been used. Please request a new one if you still need to reset your password." |
| `POST /auth/change-password`    | 400    | "We couldn't change your password. Please make sure your current password is correct..."                             |
| `GET /auth/login/{provider}`    | 404    | "This sign-in method is not available right now. Please try a different sign-in option."                             |
| `GET /auth/callback/{provider}` | 400    | "For your security, this sign-in attempt couldn't be verified. Please try signing in again."                         |

### User Endpoints

| Endpoint                 | Status | Error Example                                                                                                        |
| ------------------------ | ------ | -------------------------------------------------------------------------------------------------------------------- |
| `POST /users/create`     | 400    | "An account with this username or email already exists. Please sign in instead or use different information."        |
| `PATCH /users/{user_id}` | 400    | "An account with this email already exists. Please use a different email or sign in to your existing account."       |

### Blog Endpoints

| Endpoint                 | Status | Error Example                                                                            |
| ------------------------ | ------ | ---------------------------------------------------------------------------------------- |
| `POST /blogs/create`     | 400    | "A blog with this URL slug already exists. Please choose a different title or slug."     |
| `PATCH /blogs/{blog_id}` | 400    | "A blog with this URL slug already exists. Please choose a different title or slug."     |

---

## 🛠️ Implementation Notes

### Error Class Hierarchy

All custom errors extend `BaseAppError` and are located in `app/errors/`:

```plain text
app/errors/
├── auth.py       # Authentication errors
├── database.py   # Database errors
├── email.py      # Email service errors
├── ai.py         # AI service errors
├── upload.py     # File upload errors
├── password_hasher.py  # Password hashing errors
├── validation.py # Validation errors
└── base.py       # Base error class
```

### Using Error Messages

Error messages are automatically returned when exceptions are raised:

```python
from app.errors.auth import InvalidCredentialsError

# This will return a 401 with the friendly message
raise InvalidCredentialsError
```

### Custom Error Messages

For dynamic messages, you can pass a custom detail to some errors:

```python
from app.errors.database import DuplicateEntryError

raise DuplicateEntryError(
    detail="An account with this email already exists. Please sign in instead."
)
```

---

## 📝 Testing Error Messages

When testing API endpoints, expect these user-friendly messages in the response:

```json
{
  "detail": "Your email address hasn't been verified yet. Please check your inbox..."
}
```

---

## 🔄 Version History

| Version | Date       | Changes                                            |
| --------|----------- |-------------------------------------------------   |
| 1.0     | 2026-02-11 | Initial user-friendly error message implementation |

---

*For technical implementation details, see the source code in `app/errors/` directory.*
