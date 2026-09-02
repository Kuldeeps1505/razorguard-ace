"""Intent domain exceptions."""

from razorguard.shared.errors import IntentImmutableError, InvalidIntentError


class InvalidIntentValueError(InvalidIntentError):
    """Raised when an intent field value is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message)


class IntentAlreadyAuthorizedError(IntentImmutableError):
    """Raised when trying to modify an already-authorized intent."""

    def __init__(self, intent_id: str) -> None:
        super().__init__(intent_id=intent_id)


class IntentHashMismatchError(InvalidIntentError):
    """Raised when the computed intent hash doesn't match the stored hash."""

    def __init__(self, intent_id: str) -> None:
        super().__init__(
            message=f"Intent hash mismatch for {intent_id} — tamper detected",
            intent_id=intent_id,
        )
