"""
Monitoring and observability module for BaliBlissed Backend.

This module provides comprehensive monitoring capabilities including:
- Prometheus metrics collection
- Structured logging with PII sanitization
- Distributed tracing with OpenTelemetry
- Health checks for Kubernetes compatibility

Modules
-------
prometheus : Metrics collection with cardinality protection
logging : Structured JSON logging with security sanitization
tracing : Distributed tracing with sampling
health : Kubernetes-compatible health endpoints

Examples
--------
>>> from app.monitoring import , metrics, tracer
"""

from app.monitoring.health import HealthChecker, HealthStatus
from app.monitoring.prometheus import metrics, setup_prometheus
from app.monitoring.tracing import setup_tracing, tracer

__all__ = [
    "metrics",
    "setup_prometheus",
    "setup_tracing",
    "tracer",
    "HealthChecker",
    "HealthStatus",
]
