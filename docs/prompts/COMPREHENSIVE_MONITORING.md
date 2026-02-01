# **Implement Comprehensive Monitoring & Observability Feature Improvement**

## **Objective:**

Refactor the existing custom monitoring solution to a robust, production-grade Observability Stack using Prometheus, Structlog, and OpenTelemetry, as outlined in `IMPROVEMENTS.md` P1: High-Value Features

### **Current State Analysis:**

* **Metrics:** Currently handled by a custom `MetricsManager` in `app/managers/metrics.py` which manually counts requests/errors and uses `psutil` for system stats. It exposes a custom JSON structure at `/metrics`.
* **Logging:** Currently uses Python's standard `logging` with `python-json-logger` and `rich` in `app/middleware/middleware.py`.
* **Health:** Basic health check in `app/main.py` checking Cache and basic service presence.
* **Tracing:** No distributed tracing implemented.

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

### **Phase 2: Structured Logging (Structlog)**

* **Action:**
    1. Install `structlog` and `orjson`.
    2. Create `app/monitoring/logging.py` to configure `structlog`.
    3. **Requirements:**
        * Output must be JSON formatted for production (use `orjson` for performance).
        * Include `request_id` (correlation ID) in every log entry.
        * Include context (User ID, IP) where available.
        * Use `structlog.contextvars.merge_contextvars` processor for async context propagation.
        * Inject OpenTelemetry trace context (`trace_id`, `span_id`) into logs for trace-log correlation.
    4. **Refactor:** Replace `LoggingMiddleware` in `app/middleware/middleware.py` to use `structlog`. Update `file_logger` utility to be compatible or replace it.

### **Phase 3: Distributed Tracing (OpenTelemetry)**

* **Action:**
    1. Install `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-otlp`.
    2. Create `app/monitoring/tracing.py`.
    3. Configure the `TracerProvider` and `BatchSpanProcessor`.
    4. Instrument the FastAPI app in `app/main.py`.
    5. Configure `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` to exclude `/metrics,/health.*` from tracing.
    6. Configure sampling rate via environment variable (`OTEL_TRACES_SAMPLER_ARG`) for production cost control.
    7. *Goal:* Ensure traces connect HTTP requests to internal Database/Redis calls (where libraries support auto-instrumentation).

### **Phase 4: Enhanced Health Checks (Kubernetes-Compatible)**

* **Action:**
    1. Implement Kubernetes-compatible health endpoints:
        * `/health/live` (Liveness): Basic app responsiveness check only—**no external dependencies**. Kubernetes restarts pod on failure.
        * `/health/ready` (Readiness): Database, Redis, and dependency checks. Kubernetes stops routing traffic on failure.
        * `/health` (optional): Combined status for backward compatibility.
    2. Specific checks for **readiness** endpoint:
        * **Database:** Execute a `SELECT 1` (using `app.db` or `sqlmodel`).
        * **Redis:** Ping check.
        * **System:** Disk space & Memory usage (utilize logic from `app/managers/metrics.py` if needed).
    3. Response format should remain JSON but be more detailed.

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

## **Dependencies to Add:**

Run the following before coding:

```bash
uv add prometheus-client prometheus-fastapi-instrumentator structlog orjson opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi opentelemetry-exporter-otlp
```

## **Deliverables:**

1. **New module `app/monitoring/` with `prometheus.py`, `logging.py`, `tracing.py`**.

2. **Updated app/main.py integrating these new tools.**

3. **Cleaned up app/managers/metrics.py (remove redundant manual counting logic).**

4. **docker-compose.yaml updated to include a basic Prometheus/Jaeger configuration if applicable (or just comments on where they would fit).**

## **Constraint:**

Do not break the existing application flow. The /metrics endpoint will change format from JSON to Prometheus text format—this is intended.
