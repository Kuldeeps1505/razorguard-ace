"""
Policy Engine — deterministic authorization decision.

The engine evaluates all rules against a context and returns
exactly one decision: APPROVE | DENY | ASK_USER.

Rules:
- HARD_DENY rules are evaluated first. Any failure → DENY.
- CONSENT rules are evaluated next. Any failure → ASK_USER.
- All pass → APPROVE.

INVARIANTS:
- No LLM inside this module.
- No probabilistic logic.
- Fail closed: any exception → DENY.
- Same inputs → same output, always.
- Every rule result is recorded for the audit trail.
"""

from razorguard.domain.policy.context import IntentEvaluationContext
from razorguard.domain.policy.decisions import (
    POLICY_UNAVAILABLE,
    PolicyDecisionResult,
    RuleResult,
)
from razorguard.domain.policy.rules import CONSENT_RULES, HARD_DENY_RULES
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.infrastructure.observability.metrics import policy_decisions
from razorguard.shared.clock import utcnow
from razorguard.shared.enums import PolicyDecision

logger = get_logger(__name__)


def evaluate_policy(ctx: IntentEvaluationContext) -> PolicyDecisionResult:
    """
    Evaluate all policy rules against the intent context.

    Returns DENY if engine raises any exception (fail closed).
    """
    try:
        return _evaluate(ctx)
    except Exception as exc:
        logger.error(
            "policy_engine_exception",
            intent_id=str(ctx.intent_id),
            error=str(exc),
        )
        # Fail closed — never approve when engine errors
        return POLICY_UNAVAILABLE


def _evaluate(ctx: IntentEvaluationContext) -> PolicyDecisionResult:
    evaluated_at = utcnow()
    all_results: list[RuleResult] = []

    # ── Phase 1: Hard DENY rules ──────────────────────────
    for rule_fn in HARD_DENY_RULES:
        result = rule_fn(ctx)
        all_results.append(result)
        if not result.passed:
            decision = PolicyDecisionResult(
                decision=PolicyDecision.DENY,
                reason=result.reason,
                rule_results=tuple(all_results),
                blocking_rule=result.rule_name,
                policy_version_id=str(ctx.user_policy.policy_version_id),
                merchant_policy_id=str(ctx.merchant_policy.merchant_policy_id),
                evaluated_at=evaluated_at,
            )
            _record_metrics(decision, "user")
            logger.info(
                "policy_denied",
                intent_id=str(ctx.intent_id),
                rule=result.rule_name,
                reason=result.reason,
            )
            return decision

    # ── Phase 2: Consent threshold rules ─────────────────
    consent_required = False
    consent_reason = ""
    for rule_fn in CONSENT_RULES:
        result = rule_fn(ctx)
        all_results.append(result)
        if not result.passed:
            consent_required = True
            consent_reason = result.reason

    if consent_required:
        decision = PolicyDecisionResult(
            decision=PolicyDecision.ASK_USER,
            reason=consent_reason,
            rule_results=tuple(all_results),
            blocking_rule="CONSENT_THRESHOLD",
            policy_version_id=str(ctx.user_policy.policy_version_id),
            merchant_policy_id=str(ctx.merchant_policy.merchant_policy_id),
            evaluated_at=evaluated_at,
        )
        _record_metrics(decision, "user")
        logger.info(
            "policy_ask_user",
            intent_id=str(ctx.intent_id),
            reason=consent_reason,
        )
        return decision

    # ── Phase 3: All rules passed → APPROVE ───────────────
    decision = PolicyDecisionResult(
        decision=PolicyDecision.APPROVE,
        reason="All policy rules passed",
        rule_results=tuple(all_results),
        blocking_rule=None,
        policy_version_id=str(ctx.user_policy.policy_version_id),
        merchant_policy_id=str(ctx.merchant_policy.merchant_policy_id),
        evaluated_at=evaluated_at,
    )
    _record_metrics(decision, "user")
    logger.info("policy_approved", intent_id=str(ctx.intent_id))
    return decision


def _record_metrics(decision: PolicyDecisionResult, policy_type: str) -> None:
    policy_decisions.labels(
        decision=decision.decision.value,
        policy_type=policy_type,
    ).inc()
