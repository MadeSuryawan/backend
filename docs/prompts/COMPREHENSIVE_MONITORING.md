# **Implement Comprehensive Monitoring & Observability Feature Improvement**

## **Objective:**

Refactor the existing custom monitoring solution to a robust, production-grade Observability Stack using Prometheus, Structlog, and OpenTelemetry, as outlined in `IMPROVEMENTS.md` P1: High-Value Features

### **Current State Analysis:**

* **Metrics:** Currently handled by a custom `MetricsManager` in `app/managers/metrics.py` which manually counts requests/errors and uses `psutil` for system stats. It exposes a custom JSON structure at `/metrics`.
* **Logging:** Currently uses Python's standard `logging` with `python-json-logger` and `rich` in `app/middleware/middleware.py`.
* **Health:** Basic health check in `app/main.py` checking Cache and basic service presence.
* **Tracing:** No distributed tracing implemented.

---

## **Security & Compliance Requirements (CRITICAL)**

> **⚠️ PII/Sensitive Data Protection is Mandatory**

### **PII Redaction Requirements**

Before implementing any observability feature, ensure compliance with GDPR, CCPA, and other privacy regulations:

1. **Never log or trace these sensitive fields:**
   * Passwords, API keys, tokens (Authorization, X-API-Key headers)
   * Email addresses, phone numbers, physical addresses
   * Credit card numbers, SSNs, government IDs
   * Session IDs with high cardinality
   * Query parameters containing sensitive data

2. **Implementation Requirements:**

   ```python
   # In app/monitoring/logging.py - Sanitize headers
   SENSITIVE_HEADERS = {'authorization', 'cookie', 'x-api-key', 'proxy-authorization'}
   
   # In app/monitoring/tracing.py - Exclude sensitive attributes
   # Use OpenTelemetry Collector redaction processor as backup
   ```

3. **Validation:**
   * Add regex patterns to detect potential PII in log messages
   * Use structlog processors to redact sensitive fields automatically
   * Configure OpenTelemetry Collector with `redaction` processor

### **Metrics Endpoint Security**

```python
# In app/monitoring/prometheus.py - Restrict /metrics access
# Option 1: IP-based restriction (recommended for production)
ALLOWED_METRICS_IPS = ['127.0.0.1', '10.0.0.0/8', '172.16.0.0/12']

# Option 2: Internal metrics port (not exposed publicly)
# Run metrics on port 9090 internally, expose via reverse proxy with auth
```

---

## **Implementation Plan (Strictly Follow Phases):**

### **Phase 1: Prometheus Metrics (Replace Custom Manager)**

* **Action:**
    1. Install `prometheus-client` and `prometheus-fastapi-instrumentator`.
    2. Create `app/monitoring/prometheus.py`.
    3. Implement the `Instrumentator` using `lifespan` async context manager (not deprecated `@app.on_event`).
    4. **Refactor:** Deprecate or modify the existing `app/managers/metrics.py`. Instead of manual counters, custom logic should update Prometheus Gauges/Counters.
    5. **Custom Metrics:** Ensure the following are tracked via Prometheus:
        * Cache Hit/Miss Rates.
        * AI Request Duration & Token Usage (if available).
        * Circuit Breaker States.
        * System Stats (CPU/Memory) - *Note: The Instrumentator handles standard HTTP metrics, but you may need to keep `psutil` logic to update specific Prometheus Gauges.*

* **Cardinality Protection (CRITICAL):**

    ```python
    # ⚠️ NEVER use these as labels - causes memory exhaustion
    HIGH_CARDINALITY_LABELS = [
        'user_id',           # Unbounded unique values
        'session_id',        # Unbounded unique values
        'request_id',        # Unique per request
        'email',             # PII + high cardinality
        'full_path',         # Can include IDs like /users/12345
    ]
    
    # ✅ SAFE labels - bounded cardinality
    SAFE_LABELS = [
        'method',            # GET, POST, PUT, DELETE (4 values)
        'status_code',       # HTTP status codes (~50 values)
        'endpoint',          # Route pattern /users/{id} (bounded)
        'service',           # Known service names
    ]
    
    # Set cardinality limits
    MAX_SERIES_PER_METRIC = 10000
    MAX_LABEL_NAME_LENGTH = 128
    MAX_LABEL_VALUE_LENGTH = 1024
    ```

* **Histogram Buckets Configuration:**

    ```python
    # Configure buckets based on expected latency profile
    # For APIs with <2s response times:
    LATENCY_BUCKETS = [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    
    # For AI endpoints with longer processing:
    AI_LATENCY_BUCKETS = [0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
    ```

---

### **Phase 2: Structured Logging (Structlog)**

* **Action:**
    1. Install `structlog` and `orjson`.
    2. Create `app/monitoring/logging.py` to configure `structlog`.
    3. **Requirements:**
        * Output must be JSON formatted for production (use `orjson` for performance).
        * Include `request_id` (correlation ID) in every log entry.
        * Include context (User ID, IP) where available - **sanitized**.
        * Use `structlog.contextvars.merge_contextvars` processor for async context propagation.
        * Inject OpenTelemetry trace context (`trace_id`, `span_id`) into logs for trace-log correlation.
        * **PII Sanitization:** Redact sensitive fields before logging.
    4. **Refactor:** Replace `LoggingMiddleware` in `app/middleware/middleware.py` to use `structlog`. Update `file_logger` utility to be compatible or replace it.

* **Log Security Requirements:**

    ```python
    # Sanitize user input to prevent log injection
    def sanitize_log_message(message: str) -> str:
        """Remove newlines and control characters from log messages."""
        return message.replace('\n', '\\n').replace('\r', '\\r')
    
    # Redact sensitive headers
    def sanitize_headers(headers: dict) -> dict:
        """Return headers with sensitive values redacted."""
        sensitive = {'authorization', 'cookie', 'x-api-key'}
        return {
            k: '[REDACTED]' if k.lower() in sensitive else v
            for k, v in headers.items()
        }
    ```

---

### **Phase 3: Distributed Tracing (OpenTelemetry)**

* **Action:**
    1. Install `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-otlp`.
    2. Create `app/monitoring/tracing.py`.
    3. Configure the `TracerProvider` and `BatchSpanProcessor`.
    4. Instrument the FastAPI app in `app/main.py`.
    5. Configure `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` to exclude `/metrics,/health.*` from tracing.
    6. Configure sampling rate via environment variable (`OTEL_TRACES_SAMPLER_ARG`) for production cost control.
    7. *Goal:* Ensure traces connect HTTP requests to internal Database/Redis calls (where libraries support auto-instrumentation).

* **Sampling Strategy (IMPORTANT):**

    ```python
    # Recommended sampling configuration
    # Development: 100% sampling
    # Production: ParentBased with 10-20% sampling
    
    from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
    
    sampler = ParentBasedTraceIdRatio(
        root_ratio=0.1,  # 10% for root spans in production
        remote_parent_sampled=True,  # Honor sampling from upstream
        remote_parent_not_sampled=False,
        local_parent_sampled=True,
        local_parent_not_sampled=False,
    )
    
    # Always sample errors regardless of rate
    # Configure tail-based sampling in OTel Collector if needed
    ```

* **Resource Attributes (Semantic Conventions):**

    ```python
    from opentelemetry.sdk.resources import Resource
    
    resource = Resource.create({
        "service.name": "baliblissed-backend",
        "service.version": "1.0.0",
        "deployment.environment": settings.ENVIRONMENT,
        "host.name": os.uname().nodename,
        "service.namespace": "baliblissed",
    })
    ```

* **Graceful Degradation:**

    ```python
    # Ensure app doesn't crash if tracing backend is unavailable
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter
    
    # Fallback to console export if OTLP fails
    # Log warning but continue operating
    ```

---

### **Phase 4: Enhanced Health Checks (Kubernetes-Compatible)**

* **Action:**
    1. Implement Kubernetes-compatible health endpoints:
        * `/health/live` (Liveness): Basic app responsiveness check only—**no external dependencies**. Kubernetes restarts pod on failure.
        * `/health/ready` (Readiness): Database, Redis, and dependency checks. Kubernetes stops routing traffic on failure.
        * `/health` (optional): Combined status for backward compatibility.
    2. Specific checks for **readiness** endpoint:
        * **Database:** Execute a `SELECT 1` (using `app.db` or `sqlmodel`) with **2-second timeout**.
        * **Redis:** Ping check with **1-second timeout**.
        * **System:** Disk space & Memory usage (utilize logic from `app/managers/metrics.py` if needed).
    3. Response format should remain JSON but be more detailed.

* **Timeout Configuration (CRITICAL):**

    ```python
    # Always use timeouts for health check dependencies
    HEALTH_CHECK_TIMEOUTS = {
        'database': 2.0,  # seconds
        'redis': 1.0,
        'external_api': 3.0,
    }
    
    # Return 503 Service Unavailable immediately if timeout exceeded
    # Don't let health checks hang - causes cascading failures
    ```

* **Health Check Response Format:**

    ```json
    {
      "status": "ready",
      "timestamp": "2025-01-01T12:00:00Z",
      "version": "1.0.0",
      "checks": {
        "database": {"status": "pass", "response_ms": 15},
        "redis": {"status": "pass", "response_ms": 5},
        "disk": {"status": "pass", "usage_percent": 45}
      }
    }
    ```

---

### **Phase 5: Developer Experience (Critical)**

* **Conditional Logging:**
  * In `app/monitoring/logging.py`, check `settings.ENVIRONMENT`.
  * If `ENVIRONMENT="production"`, use `structlog.processors.JSONRenderer()` (for Datadog/CloudWatch).
  * If `ENVIRONMENT="development"`, use `structlog.dev.ConsoleRenderer()` (pretty colored output for the developer).
* **Optional Tracing:**
  * Ensure that if the OpenTelemetry Collector endpoint (Jaeger/Zipkin) is unreachable, the app **does not crash**. It should simply log a warning or fail silently.
* **Docker:**
  * Add an **OTLP Collector** to `docker-compose.yaml` as the single telemetry gateway. Optionally add Prometheus/Jaeger behind it for local visualization.
  * Ensure observability services are **not required** for the `backend` service to start healthy.

---

### **Phase 6: Grafana Visualization & Dashboards (Optional but Recommended)**

* **Purpose:** Visualize metrics with pre-configured dashboards for production monitoring.

* **Docker Compose Integration:**

    ```yaml
    # Add to docker-compose.yaml
    services:
      prometheus:
        image: prom/prometheus:latest
        volumes:
          - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
          - prometheus_data:/prometheus
        ports:
          - "9090:9090"
        networks:
          - baliblissed-network
        restart: unless-stopped

      grafana:
        image: grafana/grafana:latest
        ports:
          - "3000:3000"
        volumes:
          - grafana_data:/var/lib/grafana
          - ./monitoring/grafana/provisioning:/etc/grafana/provisioning
        environment:
          - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-admin}
          - GF_USERS_ALLOW_SIGN_UP=false
          - GF_SERVER_ROOT_URL=${GRAFANA_ROOT_URL:-http://localhost:3000}
        networks:
          - baliblissed-network
        restart: unless-stopped
        depends_on:
          - prometheus

    volumes:
      prometheus_data:
      grafana_data:
    ```

* **Dashboard Provisioning as Code:**

    ```yaml
    # monitoring/grafana/provisioning/dashboards/dashboard.yml
    apiVersion: 1
    providers:
      - name: 'BaliBlissed Dashboards'
        orgId: 1
        folder: 'BaliBlissed'
        type: file
        disableDeletion: false
        editable: true
        options:
          path: /etc/grafana/provisioning/dashboards
    ```

* **Required Dashboards:**

    | Dashboard | File | Purpose |
    | --------- | ---- | ------- |
    | **API Overview** | `fastapi-overview.json` | RPS, error rate, latency percentiles |
    | **AI Service** | `ai-service.json` | Token usage, circuit breaker status |
    | **Cache Performance** | `cache-performance.json` | Hit rate, Redis memory |
    | **Infrastructure** | `infrastructure.json` | CPU, memory, disk usage |

* **Key PromQL Queries for Dashboards:**

    ```promql
    # Request Rate (RPS)
    rate(http_requests_total[5m])

    # Error Rate Percentage
    rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])

    # P95 Latency
    histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

    # P99 Latency
    histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

    # Cache Hit Rate
    cache_hits_total / (cache_hits_total + cache_misses_total)

    # Circuit Breaker State (gauge)
    circuit_breaker_state{breaker="ai_circuit_breaker"}
    ```

* **Production Alternative:**
  * For production, consider **Grafana Cloud** (managed) or ensure your self-hosted Grafana is properly secured with HTTPS and authentication.

---

## **Dependencies to Add:**

Run the following before coding:

```bash
uv add prometheus-client prometheus-fastapi-instrumentator structlog orjson opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi opentelemetry-exporter-otlp
```

---

## **Metrics Naming Conventions:**

Follow Prometheus best practices for metric names:

```python
# Format: <namespace>_<subsystem>_<metric>_<unit>
# Use snake_case
# Add unit suffix: _seconds, _bytes, _total

# ✅ Good examples
baliblissed_cache_hits_total
baliblissed_cache_misses_total
baliblissed_ai_request_duration_seconds
baliblissed_circuit_breaker_state
baliblissed_ai_tokens_used_total

# ❌ Bad examples
cacheHitCount              # camelCase
cache_hits                 # missing _total suffix for counter
ai_request_time            # ambiguous unit (seconds? milliseconds?)
```

---

## **Testing Requirements:**

Add tests to verify observability stack:

```python
# tests/monitoring/test_metrics.py
def test_metrics_endpoint_returns_prometheus_format(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "http_requests_total" in response.text

def test_health_readiness_checks_dependencies(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert "checks" in data
    assert data["checks"]["database"]["status"] == "pass"

def test_traces_exported_to_collector():
    # Verify trace export doesn't crash app
    # Use OTEL_TRACES_EXPORTER=console in tests
    pass
```

---

## **Deliverables:**

1. **New module `app/monitoring/` with:**
   * `prometheus.py` - Metrics collection with cardinality protection
   * `logging.py` - Structured logging with PII sanitization
   * `tracing.py` - Distributed tracing with sampling
   * `__init__.py` - Export public interfaces

2. **Updated files:**
   * `app/main.py` - Integrate monitoring tools
   * `app/managers/metrics.py` - Cleaned up (remove redundant manual counting)
   * `app/middleware/middleware.py` - Use structlog for request logging

3. **Configuration:**
   * `docker-compose.yaml` - Add Prometheus, Grafana, OTLP Collector
   * `monitoring/prometheus.yml` - Prometheus scrape config
   * `monitoring/grafana/provisioning/` - Dashboard and datasource configs
   * `monitoring/grafana/dashboards/` - JSON dashboard definitions

4. **Documentation:**
   * `docs/metrics.md` - Available metrics and PromQL examples

---

## **Constraint:**

Do not break the existing application flow. The /metrics endpoint will change format from JSON to Prometheus text format—this is intended.

---

## **Pre-Deployment Checklist:**

* [ ] PII redaction tested (verify no emails/passwords in logs/traces)
* [ ] Cardinality limits enforced (no user_id, session_id as labels)
* [ ] Health check timeouts configured (DB: 2s, Redis: 1s)
* [ ] Metrics endpoint access restricted (internal IPs only)
* [ ] Sampling configured (10-20% in production)
* [ ] Graceful degradation verified (app starts without OTLP collector)
* [ ] Dashboards provisioned and tested in local Grafana
* [ ] Alert rules documented (error rate > 5%, P99 latency > 2s)
