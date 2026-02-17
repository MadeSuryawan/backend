# BaliBlissed Backend - Metrics and Observability

This document describes the comprehensive monitoring and observability stack for the BaliBlissed Backend API.

## Overview

The observability stack consists of:

1. **Prometheus Metrics** - Application and system metrics in Prometheus format
2. **Structured Logging** - JSON logs with PII sanitization using Structlog
3. **Distributed Tracing** - Request tracing with OpenTelemetry
4. **Health Checks** - Kubernetes-compatible liveness and readiness probes

## Endpoints

| Endpoint | Description | Format |
|----------|-------------|--------|
| `/metrics` | Prometheus metrics | text/plain |
| `/health/live` | Liveness probe (basic) | JSON |
| `/health/ready` | Readiness probe (with dependencies) | JSON |
| `/health` | Legacy health check | JSON |

## Prometheus Metrics

### HTTP Metrics (Auto-instrumented)

These metrics are automatically collected by `prometheus-fastapi-instrumentator`:

```promql
# Request count by handler, method, status
baliblissed_http_requests_total{handler="/users", method="GET", status="200"}

# Request duration histogram
baliblissed_http_request_duration_seconds_bucket{handler="/users", method="GET", le="0.1"}

# Requests currently in progress
baliblissed_http_requests_inprogress{handler="/users", method="GET"}

# Request size
baliblissed_http_request_size_bytes_sum

# Response size
baliblissed_http_response_size_bytes_sum
```

### Cache Metrics

```promql
# Cache hits and misses
baliblissed_cache_hits_total{cache_type="redis"}
baliblissed_cache_misses_total{cache_type="redis"}

# Cache operations
baliblissed_cache_operations_total{operation="get", status="success"}
```

### AI Service Metrics

```promql
# AI request duration
baliblissed_ai_request_duration_seconds_bucket{request_type="itinerary", le="10.0"}

# AI request count
baliblissed_ai_requests_total{request_type="itinerary", status="success"}

# AI token usage
baliblissed_ai_tokens_used_total{request_type="itinerary", token_type="input"}
baliblissed_ai_tokens_used_total{request_type="itinerary", token_type="output"}
```

### Circuit Breaker Metrics

```promql
# Circuit breaker state (0=closed, 1=open, 2=half-open)
baliblissed_circuit_breaker_state{breaker_name="ai_circuit_breaker"}

# Circuit breaker failures and successes
baliblissed_circuit_breaker_failures_total{breaker_name="ai_circuit_breaker"}
baliblissed_circuit_breaker_success_total{breaker_name="ai_circuit_breaker"}
```

### Rate Limiter Metrics

```promql
# Rate limit hits by endpoint
baliblissed_rate_limit_hits_total{endpoint="/api/users"}
```

### System Metrics

```promql
# CPU usage percentage
baliblissed_system_cpu_usage_percent

# Memory usage
baliblissed_system_memory_usage_percent
baliblissed_system_memory_used_bytes

# Disk usage
baliblissed_system_disk_usage_percent
```

## Useful PromQL Queries

### Request Rate (RPS)

```promql
rate(baliblissed_http_requests_total[5m])
```

### Error Rate Percentage

```promql
rate(baliblissed_http_requests_total{status=~"5.."}[5m]) / rate(baliblissed_http_requests_total[5m]) * 100
```

### P95 Latency

```promql
histogram_quantile(0.95, rate(baliblissed_http_request_duration_seconds_bucket[5m]))
```

### P99 Latency

```promql
histogram_quantile(0.99, rate(baliblissed_http_request_duration_seconds_bucket[5m]))
```

### Cache Hit Rate

```promql
rate(baliblissed_cache_hits_total[5m]) / (rate(baliblissed_cache_hits_total[5m]) + rate(baliblissed_cache_misses_total[5m])) * 100
```

### Slowest Endpoints (P95)

```promql
topk(5, histogram_quantile(0.95, sum by (handler, le) (rate(baliblissed_http_request_duration_seconds_bucket[5m]))))
```

### AI Service Error Rate

```promql
rate(baliblissed_ai_requests_total{status="error"}[5m]) / rate(baliblissed_ai_requests_total[5m]) * 100
```

## Health Checks

### Liveness Probe (`/health/live`)

Returns immediately without checking external dependencies. Use this for Kubernetes liveness probes.

```json
{
  "status": "pass",
  "timestamp": "2025-01-01T12:00:00Z"
}
```

**Status codes:**
- `200` - Application is alive
- `503` - Application is not responding (triggers pod restart)

### Readiness Probe (`/health/ready`)

Checks all dependencies with timeouts. Use this for Kubernetes readiness probes.

```json
{
  "status": "pass",
  "timestamp": "2025-01-01T12:00:00Z",
  "version": "1.0.0",
  "checks": {
    "database": {
      "status": "pass",
      "response_ms": 15.2
    },
    "redis": {
      "status": "pass",
      "response_ms": 5.1
    },
    "disk": {
      "status": "pass",
      "details": {
        "usage_percent": 45.2,
        "total_gb": 100.0,
        "free_gb": 54.8
      }
    },
    "memory": {
      "status": "pass",
      "details": {
        "usage_percent": 62.1,
        "total_gb": 16.0,
        "available_gb": 6.1
      }
    }
  }
}
```

**Status values:**
- `pass` - Component is healthy
- `warn` - Component has issues but is functional
- `fail` - Component is unhealthy

**Status codes:**
- `200` - Ready to receive traffic (pass or warn)
- `503` - Not ready (fail)

**Timeout Configuration:**
- Database: 2 seconds
- Redis: 1 second

## Structured Logging

Logs are output in JSON format in production and pretty console format in development.

### Log Fields

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 timestamp |
| `level` | Log level (info, warning, error) |
| `logger` | Logger name |
| `event` | Log message |
| `request_id` | Request correlation ID |
| `has_user` | Whether request has authenticated user |
| `client_ip_masked` | Masked client IP (e.g., 192.168.xxx.xxx) |
| `trace_id` | OpenTelemetry trace ID |
| `span_id` | OpenTelemetry span ID |
| `filename` | Source file |
| `lineno` | Line number |
| `func_name` | Function name |

### PII Sanitization

The following are automatically redacted from logs:

- **Headers:** Authorization, Cookie, X-API-Key, etc.
- **Fields:** password, token, api_key, credit_card, ssn, etc.
- **Patterns:** Email addresses, phone numbers, credit card numbers, SSNs

### Log Injection Prevention

Log messages are sanitized to prevent log injection attacks:
- Newlines (`\n`) and carriage returns (`\r`) are escaped
- Control characters are removed

## Distributed Tracing

OpenTelemetry is configured for distributed tracing with:

- Automatic FastAPI instrumentation
- Trace context propagation (W3C Trace Context)
- Configurable sampling rate
- OTLP export to collector

### Sampling Configuration

| Environment | Default Rate |
|-------------|-------------|
| Development | 100% |
| Production | 10% |

Override with environment variable:
```bash
OTEL_TRACES_SAMPLER_ARG=0.2  # 20% sampling
```

### Excluded Endpoints

These endpoints are excluded from tracing to reduce noise:
- `/metrics`
- `/health`, `/health/live`, `/health/ready`
- `/favicon.ico`

## Docker Compose Setup

The observability stack is included in `docker-compose.yaml`:

```bash
# Start all services including observability stack
docker-compose up -d

# View logs
docker-compose logs -f backend

# Access services:
# - Backend API: http://localhost:8000
# - Prometheus: http://localhost:9090
# - Grafana: http://localhost:3000 (admin/admin)
# - Jaeger: http://localhost:16686
```

## Grafana Dashboards

Pre-configured dashboards are available in Grafana:

1. **BaliBlissed API Overview** - Request rates, error rates, latency percentiles
2. **Cache Performance** - Cache hit rates, Redis metrics
3. **System Resources** - CPU, memory, disk usage

## Alert Rules (Recommended)

Configure these alerts in Prometheus/Alertmanager:

### High Error Rate
```yaml
- alert: HighErrorRate
  expr: rate(baliblissed_http_requests_total{status=~"5.."}[5m]) / rate(baliblissed_http_requests_total[5m]) > 0.05
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "High error rate detected"
    description: "Error rate is above 5% for 5 minutes"
```

### High Latency
```yaml
- alert: HighLatency
  expr: histogram_quantile(0.99, rate(baliblissed_http_request_duration_seconds_bucket[5m])) > 2
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High P99 latency"
    description: "P99 latency is above 2 seconds"
```

### Circuit Breaker Open
```yaml
- alert: CircuitBreakerOpen
  expr: baliblissed_circuit_breaker_state == 1
  for: 1m
  labels:
    severity: warning
  annotations:
    summary: "Circuit breaker is open"
    description: "Circuit breaker {{ $labels.breaker_name }} is open"
```

### Low Cache Hit Rate
```yaml
- alert: LowCacheHitRate
  expr: rate(baliblissed_cache_hits_total[5m]) / (rate(baliblissed_cache_hits_total[5m]) + rate(baliblissed_cache_misses_total[5m])) < 0.5
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Low cache hit rate"
    description: "Cache hit rate is below 50%"
```

## Security Considerations

### Metrics Endpoint

The `/metrics` endpoint is restricted to internal IPs by default:
- 127.0.0.1
- 10.0.0.0/8
- 172.16.0.0/12
- 192.168.0.0/16

For production, expose metrics only internally or behind authentication.

### PII Protection

- No user IDs, session IDs, or emails in metric labels
- Automatic PII redaction in logs
- Sensitive headers excluded from traces
- Request/response bodies not logged

### Cardinality Protection

High-cardinality labels are never used in metrics:
- user_id
- session_id
- request_id
- email
- full_path (use normalized route patterns)

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_METRICS` | Enable Prometheus metrics | `true` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint | `http://otel-collector:4317` |
| `OTEL_TRACES_SAMPLER_ARG` | Sampling rate (0.0-1.0) | `0.1` (production) |
| `OTEL_SERVICE_NAME` | Service name for tracing | `baliblissed-backend` |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password | `admin` |

## Troubleshooting

### Metrics Not Appearing

1. Check `/metrics` endpoint is accessible
2. Verify Prometheus is scraping the backend
3. Check Prometheus targets: http://localhost:9090/targets

### Traces Not Appearing in Jaeger

1. Check OTLP collector is running
2. Verify `OTEL_EXPORTER_OTLP_ENDPOINT` is set
3. Check collector logs: `docker-compose logs otel-collector`

### Health Check Failing

1. Check database connectivity
2. Verify Redis is running
3. Check timeout settings (may need to increase for slow networks)
