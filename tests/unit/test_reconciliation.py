"""
Unit tests — Phase 10: Reconciliation.

Tests the most important invariants of the reconciliation system:
1. UNKNOWN must never transition directly to COMPLETED or FAILED
   (must go through VERIFYING)
2. UNKNOWN always has a reconciliation path
3. Reconciliation respects max attempt limits
4. Payment is never retried — only queried
"""

import pytest

from razorguard.domain.intents.state_machine import (
    IllegalTransitionError,
    can_transition,
    validate_transition,
)
from razorguard.shared.enums import TransactionStatus


class TestUnknownReconciliationPath:
    def test_unknown_must_go_through_verifying(self):
        """
        INVARIANT: UNKNOWN → VERIFYING → COMPLETED/FAILED
        UNKNOWN cannot jump directly to COMPLETED or FAILED.
        """
        assert not can_transition(TransactionStatus.UNKNOWN, TransactionStatus.COMPLETED)
        assert not can_transition(TransactionStatus.UNKNOWN, TransactionStatus.FAILED)
        assert can_transition(TransactionStatus.UNKNOWN, TransactionStatus.VERIFYING)

    def test_verifying_can_resolve_completed(self):
        assert can_transition(TransactionStatus.VERIFYING, TransactionStatus.COMPLETED)

    def test_verifying_can_resolve_failed(self):
        assert can_transition(TransactionStatus.VERIFYING, TransactionStatus.FAILED)

    def test_unknown_cannot_retry_payment(self):
        """
        CRITICAL: UNKNOWN must NEVER transition back to EXECUTING.
        That would be a blind retry — could cause duplicate charge.
        """
        assert not can_transition(TransactionStatus.UNKNOWN, TransactionStatus.EXECUTING)
        with pytest.raises(IllegalTransitionError):
            validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.EXECUTING)

    def test_unknown_cannot_become_authorized(self):
        """Cannot re-authorize after payment was submitted."""
        assert not can_transition(TransactionStatus.UNKNOWN, TransactionStatus.AUTHORIZED)

    def test_full_reconciliation_happy_path(self):
        """
        Simulate: EXECUTING → UNKNOWN → VERIFYING → COMPLETED
        All transitions must be legal.
        """
        # Network timeout during execution
        validate_transition(TransactionStatus.EXECUTING, TransactionStatus.UNKNOWN)
        # Reconciliation starts
        validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.VERIFYING)
        # Razorpay confirms captured
        validate_transition(TransactionStatus.VERIFYING, TransactionStatus.COMPLETED)

    def test_full_reconciliation_failed_path(self):
        """
        Simulate: EXECUTING → UNKNOWN → VERIFYING → FAILED
        """
        validate_transition(TransactionStatus.EXECUTING, TransactionStatus.UNKNOWN)
        validate_transition(TransactionStatus.UNKNOWN, TransactionStatus.VERIFYING)
        validate_transition(TransactionStatus.VERIFYING, TransactionStatus.FAILED)


class TestReconciliationBackoff:
    def test_backoff_values_increase(self):
        """Backoff must be exponential — later retries wait longer."""
        from razorguard.application.reconciliation.reconcile_unknown import (
            RETRY_BACKOFF_SECONDS,
        )

        assert len(RETRY_BACKOFF_SECONDS) >= 5
        # Each subsequent backoff must be >= previous
        for i in range(1, len(RETRY_BACKOFF_SECONDS)):
            assert RETRY_BACKOFF_SECONDS[i] >= RETRY_BACKOFF_SECONDS[i - 1]

    def test_max_attempts_configured(self):
        from razorguard.application.reconciliation.reconcile_unknown import (
            MAX_RECONCILIATION_ATTEMPTS,
        )

        assert MAX_RECONCILIATION_ATTEMPTS >= 5
        assert MAX_RECONCILIATION_ATTEMPTS <= 20

    def test_backoff_covers_max_attempts(self):
        from razorguard.application.reconciliation.reconcile_unknown import (
            MAX_RECONCILIATION_ATTEMPTS,
            RETRY_BACKOFF_SECONDS,
        )

        assert len(RETRY_BACKOFF_SECONDS) >= MAX_RECONCILIATION_ATTEMPTS


class TestReconciliationNeverCreatesPayment:
    """
    Structural test: reconciliation code must only READ, never CREATE payment.
    Verified by inspecting imports.
    """

    def test_reconcile_module_does_not_import_create_order(self):
        import inspect

        from razorguard.application.reconciliation import reconcile_unknown

        source = inspect.getsource(reconcile_unknown)
        assert "create_order" not in source, "Reconciliation must NEVER create a new payment order"

    def test_reconcile_module_uses_fetch_not_create(self):
        import inspect

        from razorguard.application.reconciliation import reconcile_unknown

        source = inspect.getsource(reconcile_unknown)
        assert "fetch_payments_for_order" in source, "Reconciliation must use fetch, not create"
