# RBAC (Role-Based Access Control) Implementation Summary

## 📋 Overview

This document summarizes the completed RBAC implementation for the BaliBlissed Backend, providing a comprehensive reference for developers working with the permission system.

---

## ✅ Implementation Status

All phases of the RBAC completion plan have been successfully implemented:

- ✅ **Phase 2**: Permission System (Permission enum, `has_permission()`, `require_permission()`, `check_owner_or_admin()`)
- ✅ **Phase 3**: Permission Decorators (`@require_admin`, `@require_owner_or_admin`, `@require_permission`)
- ✅ **Phase 4**: Route Updates (Replaced 9 localhost checks with RBAC, added owner checks)
- ✅ **Phase 5**: Admin Interface (Admin routes and schemas)

**Note**: Phase 1 (RoleDB model) was deferred as the current string-based role field is sufficient for MVP.

---

## 🏗️ Architecture Overview

### Role Hierarchy

```python
ROLE_HIERARCHY = {
    "user": 0,        # Base level - standard users
    "moderator": 1,   # Mid level - content moderators
    "admin": 2,       # Highest level - system administrators
}
```

### Permission System

The system uses a **two-tier approach**:

1. **Role-based access** (RBAC) - Simple role checks for broad access control
2. **Permission-based access** - Granular permissions for fine-grained control

### Permission Enum

```python
class Permission(str, Enum):
    # Read permissions
    READ_USERS = "read:users"
    READ_BLOGS = "read:blogs"
    READ_ADMIN = "read:admin"
    
    # Write permissions
    WRITE_BLOGS = "write:blogs"
    WRITE_USERS = "write:users"
    
    # Delete permissions
    DELETE_BLOGS = "delete:blogs"
    DELETE_USERS = "delete:users"
    
    # Admin permissions
    ADMIN_ALL = "admin:all"
```

### Role-Permission Mapping

Each role has a predefined set of permissions:

- **user**: `READ_BLOGS`, `WRITE_BLOGS` (own blogs only)
- **moderator**: `READ_USERS`, `READ_BLOGS`, `WRITE_BLOGS`, `DELETE_BLOGS` (any blog)
- **admin**: All permissions including `ADMIN_ALL`

---

## 📁 File Structure

### Core Files

| File                            | Purpose                                                                                  |
| ------------------------------- | ---------------------------------------------------------------------------------------- |
| `app/auth/permissions.py`       | Permission enum, role hierarchy, permission checking functions, and FastAPI dependencies |
| `app/decorators/permissions.py` | Permission decorators for route handlers                                                 |
| `app/routes/admin.py`           | Admin-only endpoints for user and system management                                      |
| `app/schemas/admin.py`          | Admin-related Pydantic schemas                                                           |

### Modified Files

| File                     | Changes                                                           |
| ------------------------ | ----------------------------------------------------------------- |
| `app/routes/limiter.py`  | Replaced localhost check with `AdminUserDep`                      |
| `app/routes/user.py`     | Replaced 5 localhost checks, added owner checks for update/delete |
| `app/routes/blog.py`     | Replaced 6 localhost checks, added owner checks for update/delete |
| `app/main.py`            | Registered admin router                                           |
| `app/routes/__init__.py` | Added admin router export                                         |

---

## 🔧 Usage Guide

### FastAPI Dependencies (Recommended)

FastAPI dependencies are the **preferred method** for permission checking:

```python
from app.rabc import AdminUserDep, ModeratorUserDep, VerifiedUserDep
from app.rabc import require_permission, Permission

# Admin-only endpoint
@router.get("/admin-only")
async def admin_endpoint(admin_user: AdminUserDep):
    # admin_user is guaranteed to be an admin
    ...

# Moderator or higher
@router.get("/mod-only")
async def mod_endpoint(moderator_user: ModeratorUserDep):
    # moderator_user has moderator role or higher
    ...

# Permission-based
@router.get("/read-admin")
async def read_admin(
    user: Annotated[UserDB, Depends(require_permission(Permission.READ_ADMIN))]
):
    # user has READ_ADMIN permission
    ...
```

### Permission Decorators (Alternative)

Decorators are available for legacy code or special cases:

```python
from app.decorators.permissions import require_admin, require_owner_or_admin

@router.get("/admin-only")
@require_admin
async def admin_endpoint(user: UserDB):
    # user is guaranteed to be an admin
    ...

@router.put("/blogs/{blog_id}")
@require_owner_or_admin(lambda **kwargs: kwargs.get('blog').author_id)
async def update_blog(blog_id: UUID, user: UserDB, ...):
    # user must be owner or admin
    ...
```

### Owner Checks

Use the `check_owner_or_admin()` helper for manual owner verification:

```python
from app.dependencies import check_owner_or_admin

@router.put("/blogs/{blog_id}")
async def update_blog(
    blog_id: UUID,
    blog_update: BlogUpdate,
    current_user: UserDBDep,
    repo: BlogRepoDep,
):
    blog = await repo.get_by_id(blog_id)
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    
    # Check if user is owner or admin
    check_owner_or_admin(blog.author_id, current_user, "blog")
    
    # Proceed with update
    ...
```

---

## 🎯 Common Patterns

### Pattern 1: Admin-Only Endpoint

```python
from app.rabc import AdminUserDep

@router.post("/admin/action")
async def admin_action(admin_user: AdminUserDep):
    # Only admins can access this
    return {"message": "Admin action performed"}
```

### Pattern 2: Owner or Admin Access

```python
from app.dependencies import check_owner_or_admin

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    current_user: UserDBDep,
    repo: UserRepoDep,
):
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    check_owner_or_admin(user_id, current_user, "user")
    await repo.delete(user_id)
    return {"message": "User deleted"}
```

### Pattern 3: Permission-Based Access

```python
from app.rabc import require_permission, Permission

@router.get("/admin/stats")
async def get_stats(
    user: Annotated[UserDB, Depends(require_permission(Permission.READ_ADMIN))]
):
    # User must have READ_ADMIN permission
    return {"stats": "..."}
```

### Pattern 4: Role Hierarchy Check

```python
from app.rabc import has_role_or_higher

def some_business_logic(user: UserDB):
    if has_role_or_higher(user.role, "moderator"):
        # User is moderator or admin
        ...
    else:
        # Regular user
        ...
```

---

## 🔐 Admin Interface Endpoints

The admin interface provides the following endpoints (all require admin role):

| Endpoint                      | Method | Description                     |
| ----------------------------- | ------ | ------------------------------- |
| `/admin/users`                | GET    | List all users with pagination  |
| `/admin/users/{user_id}`      | GET    | Get user details including role |
| `/admin/users/{user_id}/role` | PUT    | Update user role                |
| `/admin/stats`                | GET    | Get system statistics           |

### Example: Update User Role

```python
# Request
PUT /admin/users/123e4567-e89b-12d3-a456-426614174000/role
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "role": "moderator"
}

# Response
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "username": "johndoe",
  "email": "johndoe@example.com",
  "role": "moderator",
  "isActive": true,
  "isVerified": true
}
```

---

## 📝 Important Notes

### 1. Token-Based Authentication

All RBAC checks require a valid JWT token. The `get_current_user` dependency:

- Extracts the token from the `Authorization: Bearer <token>` header
- Decodes the token and extracts `user_id`
- Looks up the user from the database
- Checks if the token is blacklisted
- Returns the `UserDB` object

### 2. Role Assignment

- New users default to `role="user"`
- Only admins can change user roles via `/admin/users/{user_id}/role`
- Role changes are immediate (no token refresh required)

### 3. Permission Inheritance

- Users with `Permission.ADMIN_ALL` automatically have all permissions
- Role hierarchy allows higher roles to access lower-role endpoints
- Permissions are checked in addition to roles (not instead of)

### 4. Owner Checks

- Owner checks allow both the resource owner AND admins
- Use `check_owner_or_admin()` for consistent error messages
- Always verify the resource exists before checking ownership

### 5. Testing RBAC

When writing tests for RBAC-protected endpoints:

```python
from app.managers.token_manager import create_access_token
from app.models import UserDB

# Create admin user and token
admin_user = UserDB(..., role="admin")
admin_token = create_access_token(
    user_id=admin_user.uuid,
    username=admin_user.username,
)

# Use token in requests
response = await client.post(
    "/admin/endpoint",
    headers={"Authorization": f"Bearer {admin_token}"},
)
```

### 6. Migration from Localhost Checks

All localhost-based authorization has been replaced with RBAC:

- **Before**: `if host(request) not in ("127.0.0.1", "::1", "localhost"):`
- **After**: `admin_user: AdminUserDep` in function parameters

This allows remote admin access (with proper authentication) while maintaining security.

---

## 🚨 Security Considerations

### 1. Token Security

- Tokens are signed with `SECRET_KEY` (never expose this)
- Tokens include `jti` (JWT ID) for blacklisting
- Tokens have expiration times (access: 30 min, refresh: 7 days)
- Revoked tokens are blacklisted in Redis

### 2. Role Escalation Prevention

- Role changes require admin authentication
- Role changes are logged (via `updated_at` timestamp)
- No automatic role escalation based on actions

### 3. Permission Granularity

- Use role-based checks for broad access control
- Use permission-based checks for fine-grained control
- Always verify both role and permission when needed

### 4. Owner Verification

- Always verify resource ownership before allowing modifications
- Admins can bypass owner checks (by design)
- Use `check_owner_or_admin()` for consistent behavior

---

## 🔍 Troubleshooting

### Issue: "Admin access required" but user is admin

**Possible causes:**

1. Token doesn't contain correct `user_id`
2. User role not set correctly in database
3. Token expired or blacklisted

**Solution:**

- Verify token contains `user_id` claim
- Check database: `SELECT uuid, username, role FROM users WHERE uuid = '<user_id>';`
- Generate new token and try again

### Issue: Permission check fails for admin

**Possible causes:**

1. `ROLE_PERMISSIONS` mapping missing admin permissions
2. Permission enum value mismatch

**Solution:**

- Check `app/auth/permissions.py` - ensure admin has `Permission.ADMIN_ALL`
- Verify permission enum value matches what's being checked

### Issue: Owner check fails for admin

**Possible causes:**

1. Using manual check instead of `check_owner_or_admin()`
2. Admin role not recognized

**Solution:**

- Use `check_owner_or_admin(owner_id, current_user, "resource_name")`
- Verify `current_user.role == "admin"`

---

## 📚 Reference

### Key Functions

| Function                                              | Location                  | Purpose                                    |
| ----------------------------------------------------- | ------------------------- | ------------------------------------------ |
| `has_permission(user, permission)`                    | `app/auth/permissions.py` | Check if user has specific permission      |
| `require_permission(permission)`                      | `app/auth/permissions.py` | FastAPI dependency factory for permissions |
| `check_owner_or_admin(owner_id, user, resource_name)` | `app/auth/permissions.py` | Verify owner or admin access               |
| `has_role_or_higher(user_role, required_role)`        | `app/auth/permissions.py` | Check role hierarchy                       |
| `require_admin()`                                     | `app/auth/permissions.py` | FastAPI dependency for admin access        |
| `require_moderator()`                                 | `app/auth/permissions.py` | FastAPI dependency for moderator+ access   |

### Type Aliases

```python
AdminUserDep = Annotated[UserDB, Depends(require_admin)]
ModeratorUserDep = Annotated[UserDB, Depends(require_moderator)]
VerifiedUserDep = Annotated[UserDB, Depends(require_verified_user)]
```

### Decorators

| Decorator                                   | Location                        | Purpose                     |
| ------------------------------------------- | ------------------------------- | --------------------------- |
| `@require_admin`                            | `app/decorators/permissions.py` | Require admin role          |
| `@require_owner_or_admin(owner_id_getter)`  | `app/decorators/permissions.py` | Require owner or admin      |
| `@require_permission_decorator(permission)` | `app/decorators/permissions.py` | Require specific permission |

---

## 🎓 Best Practices

1. **Prefer Dependencies over Decorators**: FastAPI dependencies are more flexible and testable
2. **Use Type Aliases**: `AdminUserDep` is cleaner than `Annotated[UserDB, Depends(require_admin)]`
3. **Check Resource Existence First**: Always verify resource exists before ownership checks
4. **Consistent Error Messages**: Use `check_owner_or_admin()` for consistent error messages
5. **Test with Different Roles**: Always test endpoints with user, moderator, and admin roles
6. **Document Permission Requirements**: Add comments explaining why specific permissions are required

---

## 🔄 Future Enhancements

Potential improvements for future consideration:

1. **RoleDB Model**: If permission granularity needs increase, consider implementing a RoleDB model
2. **Permission Groups**: Group related permissions for easier management
3. **Dynamic Permissions**: Allow admins to assign custom permissions to users
4. **Audit Logging**: Log all permission checks and role changes
5. **Permission Caching**: Cache user permissions in Redis for performance

---

## 📞 Quick Reference

### Common Imports

```python
# Dependencies
from app.rabc import (
    AdminUserDep,
    ModeratorUserDep,
    VerifiedUserDep,
    require_permission,
    Permission,
    check_owner_or_admin,
)

# Decorators
from app.decorators.permissions import (
    require_admin,
    require_owner_or_admin,
    require_permission_decorator,
)
```

### Quick Checks

```python
# Is user admin?
if user.role == "admin": ...

# Has permission?
if has_permission(user, Permission.READ_ADMIN): ...

# Is moderator or higher?
if has_role_or_higher(user.role, "moderator"): ...

# Is owner or admin?
check_owner_or_admin(resource_owner_id, current_user, "resource")
```

---

*Last Updated: December 2024*  
*Implementation Status: Complete*  
*Test Coverage: All tests passing*
