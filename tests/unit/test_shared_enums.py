"""
Unit tests — shared/enums.py

Terminal state protection is a hard invariant.
Test it explicitly so regressions are caught immediately.
"""

from razorguard.shared.enums import TransactionStatus


def test_terminal_states_are_terminal():
    terminal = [
        TransactionStatus.COMPLETED,
        TransactionStatus.FAILED,
        TransactionStatus.POLICY_BLOCKED,
        TransactionStatus.CONSENT_REJECTED,
        TransactionStatus.EXPIRED,
        TransactionStatus.CANCELLED,
        TransactionStatus.AGENT_STOPPED,
    ]
    for state in terminal:
        assert state.is_terminal, f"{state} should be terminal"


def test_non_terminal_states_are_not_terminal():
    non_terminal = [
        TransactionStatus.CREATED,
        TransactionStatus.VALIDATING,
        TransactionStatus.POLICY_PENDING,
        TransactionStatus.POLICY_APPROVED,
        TransactionStatus.AWAITING_CONSENT,
        TransactionStatus.CONSENT_GRANTED,
        TransactionStatus.AUTHORIZED,
        TransactionStatus.EXECUTING,
        TransactionStatus.UNKNOWN,
        TransactionStatus.VERIFYING,
    ]
    for state in non_terminal:
        assert not state.is_terminal, f"{state} should NOT be terminal"


def test_unknown_is_not_terminal():
    """
    CRITICAL: UNKNOWN must never be treated as terminal.
    It must go through reconciliation.
    """
    assert not TransactionStatus.UNKNOWN.is_terminal
