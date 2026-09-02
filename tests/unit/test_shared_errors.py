"""Unit tests — shared/errors.py"""

from razorguard.shared.errors import (
    CapabilityReplayError,
    InvalidIntentError,
    PaymentUnknownError,
    PolicyDeniedError,
    PriceChangedError,
    RazorGuardError,
)


def test_error_has_code():
    err = InvalidIntentError("bad amount", amount=-1)
    assert err.code == "INVALID_INTENT"
    assert "bad amount" in str(err)
    assert err.details["amount"] == -1


def test_policy_denied_carries_reason():
    err = PolicyDeniedError("amount exceeds limit", policy_id="p-42")
    assert err.code == "POLICY_DENIED"
    assert err.details["policy_id"] == "p-42"


def test_capability_replay_error():
    err = CapabilityReplayError("cap-123")
    assert err.code == "CAPABILITY_REPLAY"
    assert "cap-123" in str(err)


def test_payment_unknown_error():
    """UNKNOWN payment errors must be distinguishable from FAILED."""
    err = PaymentUnknownError("txn-99", "order_xyz")
    assert err.code == "PAYMENT_UNKNOWN"
    assert err.details["transaction_id"] == "txn-99"


def test_price_changed_error_shows_amounts():
    err = PriceChangedError("prod-1", 149900, 249900)
    assert err.code == "PRICE_CHANGED"
    assert err.details["original_minor"] == 149900
    assert err.details["current_minor"] == 249900
    assert "₹" in err.message


def test_all_errors_are_razorguard_errors():
    errors = [
        InvalidIntentError("x"),
        PolicyDeniedError("x"),
        CapabilityReplayError("x"),
        PaymentUnknownError("x"),
        PriceChangedError("x", 1, 2),
    ]
    for err in errors:
        assert isinstance(err, RazorGuardError)
        assert isinstance(err, Exception)
