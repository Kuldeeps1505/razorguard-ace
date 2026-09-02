"""
Policy Simulator — run a hypothetical transaction through the policy engine
without persisting anything or affecting real state.

This is the demo-facing feature that makes the policy engine VISIBLE.
Judges can enter any scenario and see exactly which rules pass/fail.

Usage:
  POST /policy/simulate
  →  Full PolicyDecisionResult with every rule result
"""

from razorguard.domain.policy.context import (
    IntentEvaluationContext,
)
from razorguard.domain.policy.decisions import PolicyDecisionResult
from razorguard.domain.policy.engine import evaluate_policy


def simulate_policy(ctx: IntentEvaluationContext) -> PolicyDecisionResult:
    """
    Run policy evaluation without any side effects.
    Returns the full decision including every rule result.
    """
    return evaluate_policy(ctx)
