"""
Prometheus metrics definitions.

All metrics in one place so they can be reviewed easily.
Never add metrics that leak PII or financial data as label values.
"""

from prometheus_client import Counter, Gauge, Histogram

# ── Payment metrics ───────────────────────────────────────────
payments_attempted = Counter(
    "razorguard_payments_attempted_total",
    "Total payment attempts",
    ["payment_method", "merchant_id"],
)
payments_successful = Counter(
    "razorguard_payments_successful_total",
    "Successful payments",
    ["payment_method"],
)
payments_failed = Counter(
    "razorguard_payments_failed_total",
    "Failed payments",
    ["reason"],
)
payments_unknown = Counter(
    "razorguard_payments_unknown_total",
    "Payments in UNKNOWN state awaiting reconciliation",
)
payments_reconciled = Counter(
    "razorguard_payments_reconciled_total",
    "Payments resolved via reconciliation",
    ["outcome"],
)

# ── Policy metrics ────────────────────────────────────────────
policy_decisions = Counter(
    "razorguard_policy_decisions_total",
    "Policy engine decisions",
    ["decision", "policy_type"],  # policy_type: user | merchant
)
policy_blocks = Counter(
    "razorguard_policy_blocks_total",
    "Transactions blocked by policy",
    ["reason"],
)

# ── Security metrics ──────────────────────────────────────────
capability_replays_rejected = Counter(
    "razorguard_capability_replays_rejected_total",
    "Capability replay attempts blocked",
)
webhook_forgeries_rejected = Counter(
    "razorguard_webhook_forgeries_rejected_total",
    "Webhooks rejected due to invalid signature",
)
prompt_injections_detected = Counter(
    "razorguard_prompt_injections_detected_total",
    "Prompt injection patterns detected in catalog content",
)
duplicate_payments_prevented = Counter(
    "razorguard_duplicate_payments_prevented_total",
    "Duplicate payment attempts deduplicated",
)

# ── Consent metrics ───────────────────────────────────────────
consent_requested = Counter(
    "razorguard_consent_requested_total",
    "Consent requests raised",
)
consent_granted = Counter(
    "razorguard_consent_granted_total",
    "Consent approvals",
)
consent_rejected = Counter(
    "razorguard_consent_rejected_total",
    "Consent rejections",
)

# ── Agent metrics ─────────────────────────────────────────────
agent_tool_calls = Counter(
    "razorguard_agent_tool_calls_total",
    "Agent tool invocations",
    ["tool_name"],
)
agent_payment_attempts = Counter(
    "razorguard_agent_payment_attempts_total",
    "Payment attempts initiated by agents",
    ["agent_id"],
)

# ── Latency ───────────────────────────────────────────────────
policy_evaluation_duration = Histogram(
    "razorguard_policy_evaluation_duration_seconds",
    "Time spent evaluating policy",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)
payment_execution_duration = Histogram(
    "razorguard_payment_execution_duration_seconds",
    "Time spent on payment execution (Razorpay round-trip)",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

# ── System ────────────────────────────────────────────────────
active_intents = Gauge(
    "razorguard_active_intents",
    "Currently active (non-terminal) intents",
)
reconciliation_queue_depth = Gauge(
    "razorguard_reconciliation_queue_depth",
    "UNKNOWN transactions awaiting reconciliation",
)
