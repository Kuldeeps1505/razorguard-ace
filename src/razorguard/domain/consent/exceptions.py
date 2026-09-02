"""Consent domain exceptions."""

from razorguard.shared.errors import RazorGuardError


class ConsentAlreadyUsedError(RazorGuardError):
    def __init__(self, consent_id: str) -> None:
        super().__init__(
            message=f"Consent {consent_id} has already been used",
            code="CONSENT_ALREADY_USED",
            details={"consent_id": consent_id},
        )


class ConsentIntentMismatchError(RazorGuardError):
    def __init__(self, consent_id: str, intent_id: str) -> None:
        super().__init__(
            message=f"Consent {consent_id} is not bound to intent {intent_id}",
            code="CONSENT_INTENT_MISMATCH",
            details={"consent_id": consent_id, "intent_id": intent_id},
        )


class ConsentNotPendingError(RazorGuardError):
    def __init__(self, consent_id: str, status: str) -> None:
        super().__init__(
            message=f"Consent {consent_id} is not in PENDING state (current: {status})",
            code="CONSENT_NOT_PENDING",
            details={"consent_id": consent_id, "status": status},
        )
