"""Prometheus metrics for certman agent observability."""
from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge, Info

# Subscribe endpoint wakeup source tracking
subscribe_wakeup_total = Counter(
    "certman_agent_subscribe_wakeup_total",
    "Total subscribe endpoint wakeups",
    ["node_id", "wakeup_source"],  # wakeup_source: "event" | "timeout"
)

subscribe_wait_duration = Histogram(
    "certman_agent_subscribe_wait_seconds",
    "Subscribe endpoint wait duration",
    ["node_id", "wakeup_source"],
    buckets=[1, 5, 10, 20, 30, 60, 120],
)

# Bundle token expiration tracking
bundle_token_expired_total = Counter(
    "certman_agent_bundle_token_expired_total",
    "Total bundle downloads rejected due to expired token",
    ["node_id", "job_id"],
)

bundle_token_invalid_total = Counter(
    "certman_agent_bundle_token_invalid_total",
    "Total bundle downloads rejected due to invalid token",
    ["node_id", "error_code"],
)

bundle_download_success_total = Counter(
    "certman_agent_bundle_download_success_total",
    "Total successful bundle downloads",
    ["node_id", "job_id"],
)

# Callback endpoint success/failure tracking
callback_result_total = Counter(
    "certman_agent_callback_result_total",
    "Total callback result reports",
    ["node_id", "status", "outcome"],  # outcome: "success" | "failure"
)

callback_result_duration = Histogram(
    "certman_agent_callback_result_seconds",
    "Callback result processing duration",
    ["node_id", "outcome"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0],
)

# General agent activity metrics
agent_poll_total = Counter(
    "certman_agent_poll_total",
    "Total agent poll requests",
    ["node_id", "endpoint"],  # endpoint: "poll" | "subscribe" | "heartbeat"
)

agent_auth_failure_total = Counter(
    "certman_agent_auth_failure_total",
    "Total agent authentication failures",
    ["node_id", "error_code"],
)

# Active nodes gauge
active_nodes = Gauge(
    "certman_active_nodes",
    "Number of currently active nodes",
)

# Server info
server_info = Info(
    "certman_server",
    "CertMan server information",
)
