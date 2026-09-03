"""
Security dashboard HTTP routes.

GET /security/dashboard — live counters from Prometheus metrics.
These are real system events, not decorative AI scores.
"""

from fastapi import APIRouter, HTTPException, status
from prometheus_client import Counter
from pydantic import BaseModel

from razorguard.infrastructure.observability import metrics as m
from razorguard.shared.config import get_settings

router = APIRouter()


class SecurityDashboardResponse(BaseModel):
    policy_violations_blocked: int
    duplicate_payments_prevented: int
    expired_capabilities_rejected: int
    prompt_injections_detected: int
    unknown_payments_reconciled: int
    webhook_replays_rejected: int
    payments_unknown: int
    consent_requested: int
    consent_granted: int
    consent_rejected: int


def _counter_total(counter: Counter) -> int:
    total = 0.0
    for family in counter.collect():
        for sample in family.samples:
            if sample.name.endswith("_total"):
                total += sample.value
    return int(total)


@router.get(
    "/dashboard",
    response_model=SecurityDashboardResponse,
    summary="Security control-plane counters",
)
async def security_dashboard() -> SecurityDashboardResponse:
    return SecurityDashboardResponse(
        policy_violations_blocked=_counter_total(m.policy_blocks),
        duplicate_payments_prevented=_counter_total(m.duplicate_payments_prevented),
        expired_capabilities_rejected=_counter_total(m.capability_replays_rejected),
        prompt_injections_detected=_counter_total(m.prompt_injections_detected),
        unknown_payments_reconciled=_counter_total(m.payments_reconciled),
        webhook_replays_rejected=_counter_total(m.webhook_forgeries_rejected),
        payments_unknown=_counter_total(m.payments_unknown),
        consent_requested=_counter_total(m.consent_requested),
        consent_granted=_counter_total(m.consent_granted),
        consent_rejected=_counter_total(m.consent_rejected),
    )


@router.post(
    "/demo-seed",
    response_model=SecurityDashboardResponse,
    summary="Development-only security telemetry seed",
)
async def seed_demo_security_signals() -> SecurityDashboardResponse:
    """Seed a few non-financial demo signals for a recorded walkthrough.

    This only changes in-process Prometheus counters. It creates no payment,
    intent, consent, capability, audit event, or database record. It is never
    available in production.
    """
    if get_settings().is_production:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )

    m.policy_blocks.labels(reason="demo_price_drift").inc(2)
    m.duplicate_payments_prevented.inc(1)
    m.capability_replays_rejected.inc(1)
    m.prompt_injections_detected.inc(2)
    m.payments_reconciled.labels(outcome="completed").inc(1)
    m.webhook_forgeries_rejected.inc(1)
    return await security_dashboard()
