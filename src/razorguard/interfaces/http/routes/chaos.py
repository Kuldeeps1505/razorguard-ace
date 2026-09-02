"""Deterministic, non-payment chaos demonstrations for security review."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ChaosRequest(BaseModel):
    scenario: str


@router.post("/simulate", summary="Simulate a controlled RazorGuard safeguard")
async def simulate_chaos(request: ChaosRequest) -> dict:
    outcomes = {
        "price_drift": ("BLOCKED", "Canonical price changed; fresh approval is required."),
        "duplicate_execution": ("BLOCKED", "Idempotency key and execution lock prevent a second charge."),
        "forged_webhook": ("BLOCKED", "Webhook signature verification rejected the event."),
        "prompt_injection": ("BLOCKED", "External catalog text is data; it cannot authorize a payment."),
        "merchant_kill_switch": ("BLOCKED", "Final merchant policy check disabled agent commerce."),
        "provider_timeout": ("UNKNOWN", "No retry was sent; reconciliation is queued."),
    }
    outcome = outcomes.get(request.scenario)
    if not outcome:
        return {"status": "INVALID_SCENARIO", "supported": sorted(outcomes)}
    return {"scenario": request.scenario, "status": outcome[0], "explanation": outcome[1], "side_effects": False}
