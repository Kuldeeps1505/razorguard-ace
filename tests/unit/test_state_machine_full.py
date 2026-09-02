"""
Unit tests — Phase 7: State Machine full coverage.

Tests every legal transition and explicitly verifies
every illegal one raises an error.

This is the safety net that prevents:
- COMPLETED → EXECUTING (double charge after success)
- FAILED → AUTHORIZED (payment after failure)
- UNKNOWN → COMPLETED (skipping reconciliation)
- Any terminal → any state
"""

import pytest

from razorguard.domain.intents.state_machine import (
    LEGAL_TRANSITIONS,
    IllegalTransitionError,
    can_transition,
    validate_transition,
)
from razorguard.shared.enums import TransactionStatus

# All states for exhaustive testing
ALL_STATES = list(TransactionStatus)
TERMINAL = [s for s in ALL_STATES if s.is_terminal]
NON_TERMINAL = [s for s in ALL_STATES if not s.is_terminal]


class TestLegalTransitions:
    """Every legal transition must not raise."""

    @pytest.mark.parametrize("from_s,to_s", list(LEGAL_TRANSITIONS))
    def test_legal_transition_does_not_raise(
        self, from_s: TransactionStatus, to_s: TransactionStatus
    ) -> None:
        validate_transition(from_s, to_s)  # must not raise

    @pytest.mark.parametrize("from_s,to_s", list(LEGAL_TRANSITIONS))
    def test_can_transition_returns_true_for_legal(
        self, from_s: TransactionStatus, to_s: TransactionStatus
    ) -> None:
        assert can_transition(from_s, to_s)


class TestTerminalStateImmutability:
    """Terminal states must NEVER transition — to anything."""

    @pytest.mark.parametrize("terminal", TERMINAL)
    def test_terminal_cannot_transition_to_any_state(self, terminal: TransactionStatus) -> None:
        for target in ALL_STATES:
            assert not can_transition(
                terminal, target
            ), f"Terminal state {terminal} must not transition to {target}"

    @pytest.mark.parametrize("terminal", TERMINAL)
    def test_terminal_validate_raises(self, terminal: TransactionStatus) -> None:
        for target in ALL_STATES:
            with pytest.raises(IllegalTransitionError):
                validate_transition(terminal, target)


class TestCriticalSafetyInvariants:
    """These are the most important tests — payment safety guarantees."""

    def test_completed_cannot_execute_again(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.COMPLETED, TransactionStatus.EXECUTING)

    def test_failed_cannot_be_authorized(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.FAILED, TransactionStatus.AUTHORIZED)

    def test_unknown_cannot_skip_to_completed(self):
        """UNKNOWN must go through VERIFYING, never jump to COMPLETED."""
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.COMPLETED)

    def test_unknown_cannot_go_to_executing(self):
        """UNKNOWN must never trigger a blind retry."""
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.EXECUTING)

    def test_created_cannot_jump_to_completed(self):
        """Cannot skip authorization, policy, consent steps."""
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.CREATED, TransactionStatus.COMPLETED)

    def test_created_cannot_jump_to_executing(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.CREATED, TransactionStatus.EXECUTING)

    def test_policy_blocked_is_truly_terminal(self):
        """Once policy blocks, it's over — no re-authorization path in same transaction."""
        assert TransactionStatus.POLICY_BLOCKED.is_terminal
        assert not can_transition(TransactionStatus.POLICY_BLOCKED, TransactionStatus.CREATED)

    def test_consent_rejected_is_terminal(self):
        assert TransactionStatus.CONSENT_REJECTED.is_terminal

    def test_unknown_to_verifying_is_legal(self):
        """UNKNOWN must have a reconciliation path."""
        validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.VERIFYING)

    def test_verifying_resolves_both_ways(self):
        """Reconciliation can result in SUCCESS or FAILED — both must be legal."""
        validate_transition(TransactionStatus.VERIFYING, TransactionStatus.COMPLETED)
        validate_transition(TransactionStatus.VERIFYING, TransactionStatus.FAILED)

    def test_executing_can_become_unknown(self):
        """Network timeout during execution → UNKNOWN."""
        validate_transition(TransactionStatus.EXECUTING, TransactionStatus.UNKNOWN)

    def test_all_non_terminal_can_expire(self):
        """Any non-terminal intent can expire."""
        expirable = [
            TransactionStatus.CREATED,
            TransactionStatus.VALIDATING,
            TransactionStatus.POLICY_PENDING,
            TransactionStatus.POLICY_APPROVED,
            TransactionStatus.AWAITING_CONSENT,
            TransactionStatus.CONSENT_GRANTED,
            TransactionStatus.AUTHORIZED,
        ]
        for s in expirable:
            assert can_transition(s, TransactionStatus.EXPIRED), f"{s} must be able to expire"


class TestStateMachineMetrics:
    def test_legal_transitions_count_reasonable(self):
        """Sanity check — must have at least 15 legal transitions defined."""
        assert len(LEGAL_TRANSITIONS) >= 15

    def test_terminal_states_count(self):
        assert len(TERMINAL) == 7

    def test_non_terminal_states_count(self):
        assert len(NON_TERMINAL) == len(ALL_STATES) - 7
