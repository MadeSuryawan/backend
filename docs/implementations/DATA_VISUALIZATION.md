# Data Visualization & Monitoring Guide

This guide provides a comprehensive overview of how to visualize, interpret, and troubleshoot application data using the BaliBlissed monitoring stack.

## 1. Monitoring Stack Access

| Tool | URL | Credentials | Primary Use Case |
| :--- | :--- | :--- | :--- |
| **Grafana** | [http://localhost:3000](http://localhost:3000) | `admin` / `admin` | High-level health & performance dashboards. |
| **Jaeger UI** | [http://localhost:16686](http://localhost:16686) | - | Distributed tracing & request bottleneck analysis. |
| **Prometheus** | [http://localhost:9090](http://localhost:9090) | - | Raw metric queries (PromQL) and target status. |

---

## 2. Grafana: High-Level Dashboards

Grafana is your primary tool for monitoring the overall health of the system.

### Pre-provisioned Dashboards

Navigate to **Dashboards > BaliBlissed** to find:

* **FastAPI Overview**:
  * **Request Rate (RPS)**: See how many users are hitting your API in real-time.
  * **Success Rate**: Monitor 2xx vs 5xx responses to catch errors early.
  * **Latency Percentiles (P95/P99)**: Understand the experience of your slowest users (e.g., "99% of users get a response in < 500ms").
* **Infrastructure**:
  * **Resource Usage**: Monitor CPU, RAM, and Disk for Redis, Jaeger, and the OTEL Collector.
  * **Network Throughput**: Visualize data flow between containers.

---

## 3. Prometheus: Raw Metrics & PromQL

Prometheus stores "time-series" data. Use the **Graph** tab to run raw queries.

### Understanding Counters vs. Rates

Most metrics in this system (like `http_requests_total`) are **Counters**—they only ever go up.

* **Raw Counter**: Querying `http_requests_total` shows a line that always climbs.
  * *Interpretation*: A steep slope = high traffic. A flat line = zero traffic.
* **Per-Second Rate**: Querying `rate(http_requests_total[5m])` shows the **intensity** of traffic.
  * *Interpretation*: Peaks on this graph represent "bursts" or "spikes" in activity.

### Useful Queries

| Query Description | PromQL |
| :--- | :--- |
| **Total Requests by Route** | `sum(http_requests_total) by (handler)` |
| **Error Rate (5xx)** | `sum(rate(http_requests_total{status=~"5.."}[5m]))` |
| **Avg Request Duration** | `rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])` |

---

## 4. Jaeger: Distributed Tracing

Jaeger allows you to follow a single request as it travels through your system.

### How to use it

1. Go to the Jaeger UI.
2. Select `baliblissed-backend` as the **Service**.
3. Click **Find Traces**.
4. Select a trace (e.g., `GET /users/create`) to see the **Timeline View**.

### Interpreting Spans

* **Root Span**: The top bar representing the total time the user waited for a response.
* **Child Spans**: The nested bars below. Each represents an internal operation.
* **Bottleneck Detection**: If a child span (like a database `INSERT`) takes up 90% of the total root span's length, you have found exactly where your performance issue lies.

---

## 5. Troubleshooting the Monitoring Stack

### Targets are "DOWN" in Prometheus

* Check `http://localhost:9090/targets`.
* If `baliblissed-backend` is down: Ensure `ENABLE_METRICS=true` is set in `.env` and the backend is running.
* If `otel-collector` is down: Ensure you started with `./scripts/run.sh start` (which enables the `otel` profile).

### Traces are missing in Jaeger

* Verify `OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"` is set in your `.env`.
* Check that the Jaeger container is healthy: `docker ps`.

### Logs are "Noisy"

* By default, logs for `/metrics` and `/health` are excluded to keep your console clean.
* Modify `LOG_EXCLUDED_PATHS` in `app/configs/settings.py` if you need to see these logs for debugging.
