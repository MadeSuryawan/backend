# Refactoring for Idempotency & Retry Safety

## **Objective:**

Audit and refactor the application's retry logic (`@with_retry`) to ensure **Idempotency** and prevent **Duplicate Costs**.

## **Context:**

The codebase uses a custom retry decorator (`app/decorators/with_retry.py`) based on `tenacity`. Currently, this might be applied too broadly.
We need to restrict its usage to prevent logical errors (duplicate database rows) and financial waste (double AI token usage).

## **Refactoring Rules (Strict Compliance):**

### **1. The "Cost-Safety" Rule (AI Services)**

* **Target:** `app/services/itinerary.py`, `app/routes/ai.py`, `app/clients/ai_client.py`.
* **Action:** **DISABLE automatic retries** for any AI generation calls.
* **Reasoning:** AI calls are expensive and non-idempotent (results vary by `temperature`). A timeout retry results in double-billing for the same user request.
* **Implementation:** Remove `@with_retry` from these functions. If the AI service fails/times out, the application must fail fast and let the frontend handle the decision to try again.

### **2. The "Creation-Safety" Rule (POST Endpoints)**

* **Target:** `app/routes/auth.py` (Register), `app/routes/blog.py` (Create Blog).
* **Action:** **REMOVE retries** from all `POST` endpoints that create resources *unless* you implement an Idempotency Key mechanism.
* **Reasoning:**
  * **Registration:** Retrying a "Register" call causes a `UniqueConstraintViolation` (username/email exists) on the second attempt, which confuses the user with an error despite success.
  * **Resource Creation:** Retrying a "Create Blog" call creates duplicate blog posts if the first one succeeded but the network dropped the response.
* **Fix:** Ensure these endpoints do not use `@with_retry`.

### **3. The "Update-Safety" Rule (PUT/DELETE)**

* **Target:** `app/routes/blog.py` (Update), `app/routes/items.py`.
* **Action:** **KEEP or ENABLE retries** for `PUT` (Update) and `DELETE` operations.
* **Reasoning:**
  * **PUT:** Setting a blog title to "Bali Trip" twice results in the same final state.
  * **DELETE:** Deleting a key/row twice results in the same final state (it's gone).

### **4. Redis & Cache Operations**

* **Target:** `app/services/cache.py`, `app/decorators/caching.py`.
* **Action:** Retries are **PERMITTED** for Redis `get/set/delete` operations as they are generally idempotent and prone to transient network blips.

## **Deliverable:**

Please scan the `app/routes/` and `app/clients/` directories. Apply the changes above to ensure that no `POST` request or AI Costly operation is wrapped in a blind retry loop.
