# Documentation: User Testimonial Feature

Implementation details for the user testimonial feature, providing a RESTful API for users to manage their personal testimonials.

## Database Schema

- **Table:** `users`
- **Column:** `testimonial`
- **Type:** `VARCHAR(500)`
- **Constraints:** Nullable, No index.

## API Specifications

### 1. Update Testimonial

- **Endpoint:** `PATCH /users/{user_id}/testimonial`
- **Request Body:**

  ```json
  {
    "testimonial": "Your testimonial text here..."
  }
  ```

- **Authorization:** Only the owner or an administrator.
- **Rate Limit:** 10/hour (API Key) or 5/hour (IP).
- **Cache Policy:** Invalidates the user profile cache (`users:u:{user_id}`).

### 2. Delete Testimonial

- **Endpoint:** `DELETE /users/{user_id}/testimonial`
- **Response:** `204 No Content`
- **Authorization:** Only the owner or an administrator.
- **Cache Policy:** Invalidates the user profile cache.

---

## Technical Details

### Dependency Injection

The `PATCH` endpoint uses `UserOpsDeps` to group common dependencies:

```python
@dataclass(frozen=True)
class UserOpsDeps:
    user_id: UUID
    repo: UserRepoDep
    current_user: UserDBDep
```

### Security & Validation

- **Ownership Check**: Enforced via `_get_authorized_user(repo, user_id, current_user, "testimonial")`.
- **Length Constraint**: Pydantic validates the 500-character limit during the request.
- **Idempotency**: `PATCH` allows overwriting existing testimonials safely.

---

## Frontend Implementation Guidance

The frontend should treat the testimonial as a **profile attribute** that can be in three states: *Missing*, *Present*, or *Deleting*.

### 1. UI State Management

- **Empty State**: If `user.testimonial` is `null`, display an **"Add Testimonial"** button. This should open a modal with an empty textarea.
- **Populated State**: If a testimonial exists, display the text with an **"Edit"** (Pencil) and **"Delete"** (Trash) icon nearby.
- **Editing**: The "Edit" action should open the same modal but pre-fill the textarea with the existing string.

### 2. Interaction Flow

- **Save Action**: Use `PATCH` for both initial creation and subsequent edits.
- **Delete Action**: Use the explicit `DELETE` endpoint. Upon success (204), the frontend should local-update the user model to `testimonial: null` and return to the "Empty State".
- **Validation**: Implement a character counter in the UI to prevent users from exceeding the 500-character limit before they even hit the API.

---

## Verification

### Manual Verification

1. Log in.
2. `PATCH /users/{me}/testimonial` with text.
3. Observe profile refresh (verify `testimonial` appears).
4. `DELETE /users/{me}/testimonial`.
5. Observe profile refresh (verify `testimonial` is `null`).

### Automated Tests

Run the dedicated suite:

```bash
uv run pytest tests/routes/test_user_testimonial.py
```
