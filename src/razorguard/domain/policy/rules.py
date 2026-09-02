"""
Policy rules — each rule is a pure function.

Pure functions: same inputs always produce same output.
No LLM. No database calls. No side effects.
Each rule returns a RuleResult.

Rules are evaluated in order. First DENY wins.
ASK_USER rules accumulate — if any triggers, result is ASK_USER.
All rules must pass for APPROVE.
"""

from razorguard.domain.policy.context import IntentEvaluationContext
from razorguard.domain.policy.decisions import RuleResult
from razorguard.shared.utils import paise_to_rupees

# ── Agent / delegation rules ──────────────────────────────


def rule_agent_active(ctx: IntentEvaluationContext) -> RuleResult:
    passed = ctx.agent_active
    return RuleResult(
        rule_name="AGENT_ACTIVE",
        passed=passed,
        reason="Agent is active" if passed else "Agent is suspended or revoked",
    )


def rule_delegation_active(ctx: IntentEvaluationContext) -> RuleResult:
    passed = ctx.delegation_active
    return RuleResult(
        rule_name="DELEGATION_ACTIVE",
        passed=passed,
        reason="Delegation is active" if passed else "No active delegation for this agent",
    )


# ── Merchant policy rules ─────────────────────────────────


def rule_merchant_agent_commerce_enabled(ctx: IntentEvaluationContext) -> RuleResult:
    """Kill switch — merchant can disable all agent commerce instantly."""
    passed = ctx.merchant_policy.agent_commerce_enabled
    return RuleResult(
        rule_name="MERCHANT_AGENT_COMMERCE_ENABLED",
        passed=passed,
        reason="Merchant has agent commerce enabled"
        if passed
        else "Merchant has disabled agent commerce",
    )


def rule_merchant_max_order(ctx: IntentEvaluationContext) -> RuleResult:
    max_v = ctx.merchant_policy.max_autonomous_order_minor
    actual = ctx.final_amount_minor
    passed = actual <= max_v
    return RuleResult(
        rule_name="MERCHANT_MAX_ORDER",
        passed=passed,
        reason=(
            f"Amount {paise_to_rupees(actual)} within merchant max " f"{paise_to_rupees(max_v)}"
        )
        if passed
        else (
            f"Amount {paise_to_rupees(actual)} exceeds merchant max " f"{paise_to_rupees(max_v)}"
        ),
        rule_value=str(max_v),
        actual_value=str(actual),
    )


def rule_merchant_payment_method(ctx: IntentEvaluationContext) -> RuleResult:
    allowed = ctx.merchant_policy.allowed_payment_methods
    method = ctx.payment_method.upper()
    passed = not allowed or method in allowed
    return RuleResult(
        rule_name="MERCHANT_PAYMENT_METHOD",
        passed=passed,
        reason=f"Payment method {method} allowed by merchant"
        if passed
        else f"Payment method {method} not allowed by merchant (allowed: {allowed})",
        rule_value=str(allowed),
        actual_value=method,
    )


# ── User policy rules ─────────────────────────────────────


def rule_max_single_transaction(ctx: IntentEvaluationContext) -> RuleResult:
    max_v = ctx.user_policy.max_single_transaction_minor
    actual = ctx.final_amount_minor
    passed = actual <= max_v
    return RuleResult(
        rule_name="MAX_SINGLE_TRANSACTION",
        passed=passed,
        reason=(f"Amount {paise_to_rupees(actual)} within limit {paise_to_rupees(max_v)}")
        if passed
        else (f"Amount {paise_to_rupees(actual)} exceeds limit {paise_to_rupees(max_v)}"),
        rule_value=str(max_v),
        actual_value=str(actual),
    )


def rule_daily_limit(ctx: IntentEvaluationContext) -> RuleResult:
    limit = ctx.user_policy.daily_limit_minor
    spent = ctx.spending.daily_spend_minor
    actual = ctx.final_amount_minor
    remaining = limit - spent
    passed = actual <= remaining
    return RuleResult(
        rule_name="DAILY_LIMIT",
        passed=passed,
        reason=(
            f"Daily spend OK: {paise_to_rupees(spent + actual)} of " f"{paise_to_rupees(limit)}"
        )
        if passed
        else (
            f"Daily limit exceeded: spent {paise_to_rupees(spent)}, "
            f"limit {paise_to_rupees(limit)}, "
            f"need {paise_to_rupees(actual)}"
        ),
        rule_value=str(limit),
        actual_value=str(spent + actual),
    )


def rule_category_allowed(ctx: IntentEvaluationContext) -> RuleResult:
    allowed = ctx.user_policy.allowed_categories
    cat = ctx.category.lower()
    # Empty list = all categories allowed
    passed = not allowed or cat in [c.lower() for c in allowed]
    return RuleResult(
        rule_name="CATEGORY_ALLOWED",
        passed=passed,
        reason=f"Category '{cat}' is allowed"
        if passed
        else f"Category '{cat}' is not in allowed list: {allowed}",
        rule_value=str(allowed),
        actual_value=cat,
    )


def rule_merchant_allowed(ctx: IntentEvaluationContext) -> RuleResult:
    allowlist = ctx.user_policy.allowed_merchant_ids
    blocklist = ctx.user_policy.blocked_merchant_ids
    mid = str(ctx.merchant_id)

    if blocklist and mid in blocklist:
        return RuleResult(
            rule_name="MERCHANT_ALLOWED",
            passed=False,
            reason=f"Merchant {mid} is in the blocked list",
            rule_value="blocklist",
            actual_value=mid,
        )
    passed = not allowlist or mid in allowlist
    return RuleResult(
        rule_name="MERCHANT_ALLOWED",
        passed=passed,
        reason=f"Merchant {mid} is allowed"
        if passed
        else f"Merchant {mid} is not in the allowlist",
        rule_value=str(allowlist),
        actual_value=mid,
    )


def rule_currency_allowed(ctx: IntentEvaluationContext) -> RuleResult:
    allowed = ctx.user_policy.allowed_currencies
    cur = ctx.currency.upper()
    passed = not allowed or cur in [c.upper() for c in allowed]
    return RuleResult(
        rule_name="CURRENCY_ALLOWED",
        passed=passed,
        reason=f"Currency {cur} is allowed"
        if passed
        else f"Currency {cur} not in allowed list: {allowed}",
        rule_value=str(allowed),
        actual_value=cur,
    )


def rule_consent_threshold(ctx: IntentEvaluationContext) -> RuleResult:
    """
    Not a hard DENY — returns ASK_USER if amount exceeds threshold.
    The caller (engine) interprets a False result as ASK_USER, not DENY.
    """
    threshold = ctx.user_policy.require_consent_above_minor
    actual = ctx.final_amount_minor
    passed = False if threshold == 0 else actual <= threshold
    return RuleResult(
        rule_name="CONSENT_THRESHOLD",
        passed=passed,
        reason=(
            f"Amount {paise_to_rupees(actual)} below consent threshold "
            f"{paise_to_rupees(threshold)}, auto-approve"
        )
        if passed
        else (
            f"Amount {paise_to_rupees(actual)} exceeds consent threshold "
            f"{paise_to_rupees(threshold)}, user approval required"
        ),
        rule_value=str(threshold),
        actual_value=str(actual),
    )


# ── Rule registry ─────────────────────────────────────────
# Hard DENY rules — if any fails, result is DENY regardless.
HARD_DENY_RULES = [
    rule_agent_active,
    rule_delegation_active,
    rule_merchant_agent_commerce_enabled,
    rule_merchant_max_order,
    rule_merchant_payment_method,
    rule_max_single_transaction,
    rule_daily_limit,
    rule_category_allowed,
    rule_merchant_allowed,
    rule_currency_allowed,
]

# Soft rules — if any fails, result is ASK_USER (not DENY).
CONSENT_RULES = [
    rule_consent_threshold,
]
