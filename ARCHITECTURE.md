# Production Roadmap: FastAPI + Zuplo + Render + Neon

This document outlines the architecture and deployment steps to build a scalable, secure API stack.

**The Stack:**

* **Gateway:** Zuplo (Traffic management, Authentication, Rate Limiting)
* **Compute:** Render (Hosting the FastAPI Python code)
* **Database:** Neon (Serverless Postgres)
* **Framework:** FastAPI (Python)

---

## Phase 1: Database Setup (Neon Postgres)

*Goal: Create a resilient data store that allows connections from serverless environments.*

1. **Create Project:** Log in to [Neon Console](https://console.neon.tech/) and create a project.
2. **Get Connection String:**
    * Navigate to the **Dashboard**.
    * Select **Pooled Connection** (Checkbox).
    * Copy the connection string (e.g., `postgres://user:pass@ep-pool.neon.tech/neondb`).
    * *Why Pooled?* FastAPI + Render opens connections rapidly. Pooling prevents hitting Postgres connection limits.
3. **Production Configuration:**
    * **Upgrade Plan:** Move to the **Launch Plan** (essential for production).
    * **Disable Autosuspend:** Go to **Settings** -> **Compute** -> **Scale to Zero**. Set to **Never**.
    * *Note:* If you skip this, the first API request will time out while the DB wakes up.

---

## Phase 2: Backend Deployment (Render)

*Goal: Host the FastAPI application.*

### 1. Project Preparation

Ensure your project has a `requirements.txt` and the correct start command.

* **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
* **Database Config:** Ensure you use `os.getenv("DATABASE_URL")` in your code (e.g., with SQLAlchemy or SQLModel).

### 2. Create Web Service

1. Connect your GitHub repo to Render.
2. Select **Web Service**.
3. **Runtime:** Python 3.
4. **Region:** Select the same region as your Neon DB (e.g., US East).
5. **Environment Variables:**
    * Key: `DATABASE_URL`
    * Value: `[Your Neon Pooled Connection String]`

### 3. Instance Sizing

* **Recommended:** **Standard Plan** (or at least Starter).
* *Why:* The Free tier spins down after 15 minutes of inactivity. This causes timeouts at the Gateway level.

---

## Phase 3: The Security Handshake (FastAPI Middleware)

*Goal: Ensure no one can bypass Zuplo and hit Render directly.*

We will use a **Shared Secret**. Only requests containing a specific header will be processed by FastAPI.

### 1. Generate Secret

Create a strong random string (e.g., `s3cr3t-h4ndsh4k3-k3y`).

### 2. Add to Render Environment

In Render Dashboard -> **Environment Variables**, add:

* Key: `ZUPLO_SECRET_KEY`
* Value: `[Your Generated String]`

### 3. Update FastAPI Code

Add a security dependency in your `main.py` to check for this header.

```python
import os
from fastapi import FastAPI, Header, HTTPException, Depends

app = FastAPI()

# Security Dependency
async def verify_gateway(x_zuplo_secret: str = Header(None)):
    expected_secret = os.getenv("ZUPLO_SECRET_KEY")
    
    # Allow local development to bypass (optional)
    if os.getenv("ENVIRONMENT") == "development":
        return

    if x_zuplo_secret != expected_secret:
        raise HTTPException(
            status_code=403, 
            detail="Forbidden: Access allowed only via API Gateway"
        )

# Apply globally or to specific routers
# Option A: Protect the whole app (recommended for this stack)
app = FastAPI(dependencies=[Depends(verify_gateway)])

@app.get("/")
def read_root():
    return {"message": "Hello from the secure backend!"}
```

### 4. Deploy: Push this code

Your Render URL (xxx.onrender.com) should now return a 403 Forbidden error if visited directly.

---

## Phase 4: API Gateway (Zuplo)

*Goal: Open the public front door and route traffic securely.*

1. **Create Project:** Sign up at [Zuplo](https://zuplo.com) and create a new project.
2. **Import OpenAPI (The Superpower):**
    * FastAPI auto-generates a spec at `/openapi.json`.
    * In Zuplo, create a new route via "Import OpenAPI" and point it to your Render URL: `https://your-render-app.onrender.com/openapi.json`.
    * *Benefit:* This automatically sets up all your routes in Zuplo without manual typing.
3. **Configure Backend:**
    * Ensure your **Target** (Upstream) in Zuplo is set to `https://your-render-app.onrender.com`.
4. **Configure the Secret Handshake:**
    * In Zuplo, go to **Settings** -> **Environment Variables**.
    * Add `SECRET_KEY` with the value: `[Your Generated String from Phase 3]`.
    * Go to your **Routes.json** (or use the visual designer).
    * Add a **Request Policy** of type **"Set Headers"** (or `zuplo/set-request-headers`).
    * Configuration:
        * **Header Name:** `x-zuplo-secret`
        * **Value:** `$env(SECRET_KEY)`
5. **Deploy Zuplo:**
    * Click Deploy. Your API is now live at `https://api.your-project.zuplo.app`.
    * **The Flow:** Zuplo receives the request -> Adds the secret header -> Render validates it -> Success.

[Image of API Gateway authentication flow diagram]

---

## Phase 5: Production Features (Zuplo)

*Goal: Add features without touching your Python code.*

1. **Rate Limiting:**
    * In Zuplo, add a "Rate Limit" policy to your routes.
    * *Config:* Set it to `100` requests per `minute` per `user`. This protects your Render backend and Neon database from being overwhelmed.
2. **API Key Auth:**
    * Add an "API Key Authentication" policy.
    * Zuplo handles issuing keys to users via their consumer portal.
    * Your FastAPI app doesn't need to implement user tables or logic—it simply trusts that if the request arrives, Zuplo has already verified the key.

---

## Phase 6: Recommended Add-Ons (FastAPI Specific)

### 1. Caching & Background Tasks: **Upstash (Serverless Redis)**

FastAPI is built for speed and async operations. If you are querying Neon for data that doesn't change often, or if you need to run background jobs, use Redis.

* **Why Upstash?** Like Neon, it is serverless and HTTP-based (connection friendly). It has a generous free tier.
* **Use Case:** Cache heavy database results or use it as a broker for Celery/ARQ tasks so your API returns responses instantly.

### 2. Error Monitoring: **Sentry**

Render logs are transient (they disappear when you redeploy). If your Python code crashes while you are asleep, you need to know why.

* **Implementation:** `pip install sentry-sdk`
* **FastAPI Integration:**

    ```python
    import sentry_sdk
    
    sentry_sdk.init(
        dsn="[YOUR SENTRY DSN]",
        traces_sample_rate=1.0,
    )
    ```

* **Benefit:** You get email alerts immediately when your API throws a `500 Internal Server Error` with the exact line of code that failed.

### 3. Interactive Docs: **Scalar (via Zuplo)**

While FastAPI has Swagger UI built-in (`/docs`), Zuplo offers a generic "Developer Portal".

* **Action:** Enable the "Developer Portal" in Zuplo settings.
* **Result:** It creates a Stripe-like documentation site automatically based on your FastAPI `openapi.json`, which you can share publicly with your API users.
