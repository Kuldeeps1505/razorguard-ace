"""
Intent / Transaction state machine.

Defines the ONLY legal transitions.
Any transition not in this map is REJECTED.
Terminal states are immutable — no transitions out.

This is one of the most important safety components:
it prevents, e.g., COMPLETED → EXECUTING or FAILED → AUTHORIZED.
"""

from razorguard.shared.enums import TransactionStatus
from razorguard.shared.errors import RazorGuardError

# Every legal (from_state, to_state) pair.
# Anything not in this set is ILLEGAL.
LEGAL_TRANSITIONS: frozenset[tuple[TransactionStatus, TransactionStatus]] = frozenset(
    [
        # Happy path
        (TransactionStatus.CREATED, TransactionStatus.VALIDATING),
        (TransactionStatus.VALIDATING, TransactionStatus.POLICY_PENDING),
        (TransactionStatus.POLICY_PENDING, TransactionStatus.POLICY_APPROVED),
        (TransactionStatus.POLICY_PENDING, TransactionStatus.POLICY_BLOCKED),
        (TransactionStatus.POLICY_APPROVED, TransactionStatus.AWAITING_CONSENT),
        (TransactionStatus.POLICY_APPROVED, TransactionStatus.AUTHORIZED),  # auto-approve path
        (TransactionStatus.AWAITING_CONSENT, TransactionStatus.CONSENT_GRANTED),
        (TransactionStatus.AWAITING_CONSENT, TransactionStatus.CONSENT_REJECTED),
        (TransactionStatus.CONSENT_GRANTED, TransactionStatus.AUTHORIZED),
        (TransactionStatus.AUTHORIZED, TransactionStatus.EXECUTING),
        # An order creation is submission, never proof of captured payment.
        (TransactionStatus.EXECUTING, TransactionStatus.SUBMITTED),
        (TransactionStatus.SUBMITTED, TransactionStatus.COMPLETED),
        (TransactionStatus.SUBMITTED, TransactionStatus.FAILED),
        (TransactionStatus.SUBMITTED, TransactionStatus.UNKNOWN),
        (TransactionStatus.EXECUTING, TransactionStatus.UNKNOWN),  # network timeout
        # Reconciliation path (UNKNOWN is never terminal)
        (TransactionStatus.UNKNOWN, TransactionStatus.VERIFYING),
        (TransactionStatus.VERIFYING, TransactionStatus.COMPLETED),
        (TransactionStatus.VERIFYING, TransactionStatus.FAILED),
        # Cancellation / expiry (any non-terminal state)
        (TransactionStatus.CREATED, TransactionStatus.EXPIRED),
        (TransactionStatus.VALIDATING, TransactionStatus.EXPIRED),
        (TransactionStatus.POLICY_PENDING, TransactionStatus.EXPIRED),
        (TransactionStatus.POLICY_APPROVED, TransactionStatus.EXPIRED),
        (TransactionStatus.AWAITING_CONSENT, TransactionStatus.EXPIRED),
        (TransactionStatus.CONSENT_GRANTED, TransactionStatus.EXPIRED),
        (TransactionStatus.AUTHORIZED, TransactionStatus.EXPIRED),
        (TransactionStatus.AUTHORIZED, TransactionStatus.CANCELLED),
        (TransactionStatus.AUTHORIZED, TransactionStatus.AGENT_STOPPED),
        (TransactionStatus.EXECUTING, TransactionStatus.AGENT_STOPPED),
        (TransactionStatus.SUBMITTED, TransactionStatus.AGENT_STOPPED),
    ]
)


class IllegalTransitionError(RazorGuardError):
    def __init__(self, from_state: TransactionStatus, to_state: TransactionStatus) -> None:
        super().__init__(
            message=f"Illegal state transition: {from_state} → {to_state}",
            code="ILLEGAL_STATE_TRANSITION",
            details={"from_state": from_state.value, "to_state": to_state.value},
        )


def validate_transition(
    current: TransactionStatus,
    target: TransactionStatus,
) -> None:
    """
    Assert the transition is legal. Raises IllegalTransitionError if not.

    Terminal states can NEVER transition — checked first.
    """
    if current.is_terminal:
        raise IllegalTransitionError(current, target)
    if (current, target) not in LEGAL_TRANSITIONS:
        raise IllegalTransitionError(current, target)


def can_transition(current: TransactionStatus, target: TransactionStatus) -> bool:
    """Return True if the transition is legal, without raising."""
    if current.is_terminal:
        return False
    return (current, target) in LEGAL_TRANSITIONS
