"""
Policy engine output types.

The policy engine outputs EXACTLY one of three decisions — never a boolean.
Every decision carries: reason, rule that triggered, policy version.

SECURITY:
- No LLM inside authorization logic
- No probabilistic decision for hard safety rules
- Fail closed: if engine cannot decide, return DENY
- Deterministic: same inputs always produce same output
"""

from dataclasses import dataclass, field
from datetime import datetime

from razorguard.shared.enums import PolicyDecision


@dataclass(frozen=True)
class RuleResult:
    """Result of evaluating a single policy rule."""

    rule_name: str
    passed: bool
    reason: str
    rule_value: str = ""  # e.g. "max=₹5,000"
    actual_value: str = ""  # e.g. "actual=₹6,000"


@dataclass(frozen=True)
class PolicyDecisionResult:
    """
    Complete output of policy engine evaluation.

    decision: APPROVE | DENY | ASK_USER
    rule_results: every rule checked, in order
    blocking_rule: the first rule that caused non-APPROVE (if any)
    policy_version_id: which version was evaluated (for audit)
    evaluated_at: timestamp for audit trail
    """

    decision: PolicyDecision
    reason: str
    rule_results: tuple[RuleResult, ...] = field(default_factory=tuple)
    blocking_rule: str | None = None
    policy_version_id: str | None = None
    merchant_policy_id: str | None = None
    evaluated_at: datetime | None = None

    @property
    def approved(self) -> bool:
        return self.decision == PolicyDecision.APPROVE

    @property
    def denied(self) -> bool:
        return self.decision == PolicyDecision.DENY

    @property
    def needs_consent(self) -> bool:
        return self.decision == PolicyDecision.ASK_USER

    def __str__(self) -> str:
        return f"PolicyDecision({self.decision.value}: {self.reason})"


# Sentinel — returned when policy engine is unavailable (fail closed)
POLICY_UNAVAILABLE = PolicyDecisionResult(
    decision=PolicyDecision.DENY,
    reason="Policy engine unavailable — failing closed",
    blocking_rule="POLICY_UNAVAILABLE",
)
