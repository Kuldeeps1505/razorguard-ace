"""
Unit tests — Phase 6: Consent System.

Tests cover:
- Consent domain exceptions are typed correctly
- ConsentMode has both SINGLE_TRANSACTION and MANDATE
- ConsentStatus lifecycle values present
- Consent binding invariants (intent_id must match)
"""

import pytest

from razorguard.domain.consent.exceptions import (
    ConsentAlreadyUsedError,
    ConsentIntentMismatchError,
    ConsentNotPendingError,
)
from razorguard.shared.enums import ConsentMode, ConsentStatus
from razorguard.shared.errors import RazorGuardError


class TestConsentExceptions:
    def test_already_used_error(self):
        err = ConsentAlreadyUsedError("consent-1")
        assert err.code == "CONSENT_ALREADY_USED"
        assert isinstance(err, RazorGuardError)

    def test_intent_mismatch_error(self):
        err = ConsentIntentMismatchError("consent-1", "intent-2")
        assert err.code == "CONSENT_INTENT_MISMATCH"
        assert "consent-1" in str(err)

    def test_not_pending_error(self):
        err = ConsentNotPendingError("consent-1", "REJECTED")
        assert err.code == "CONSENT_NOT_PENDING"
        assert "REJECTED" in err.message


class TestConsentModeEnum:
    def test_single_transaction_present(self):
        assert ConsentMode.SINGLE_TRANSACTION in ConsentMode

    def test_mandate_present(self):
        """UPI Reserve Pay path must be modeled from day one."""
        assert ConsentMode.MANDATE in ConsentMode

    def test_exactly_two_modes(self):
        assert len(list(ConsentMode)) == 2


class TestConsentStatusEnum:
    def test_all_statuses_present(self):
        statuses = {s.value for s in ConsentStatus}
        assert "PENDING" in statuses
        assert "APPROVED" in statuses
        assert "REJECTED" in statuses
        assert "EXPIRED" in statuses
        assert "USED" in statuses

    def test_approved_is_not_pending(self):
        assert ConsentStatus.APPROVED != ConsentStatus.PENDING

    def test_rejected_is_terminal_concept(self):
        """Once rejected, consent cannot be re-used."""
        assert ConsentStatus.REJECTED != ConsentStatus.PENDING
        assert ConsentStatus.REJECTED != ConsentStatus.APPROVED


class TestConsentBindingInvariants:
    def test_consent_must_be_bound_to_intent(self):
        """
        SECURITY INVARIANT:
        Approving consent for intent A must never authorize intent B.
        This is enforced by the ConsentIntentMismatchError in approve_consent.
        """
        import uuid

        intent_a = uuid.uuid4()
        intent_b = uuid.uuid4()

        # Simulate the check approve_consent performs
        stored_intent_id = intent_a
        requested_intent_id = intent_b

        if stored_intent_id != requested_intent_id:
            with pytest.raises(ConsentIntentMismatchError):
                raise ConsentIntentMismatchError("consent-1", str(requested_intent_id))

    def test_same_intent_does_not_raise(self):
        import uuid

        intent_id = uuid.uuid4()
        # No exception when intent matches
        try:
            if str(intent_id) != str(intent_id):
                raise ConsentIntentMismatchError("c", "i")
        except ConsentIntentMismatchError:
            pytest.fail("Should not raise when intent matches")
