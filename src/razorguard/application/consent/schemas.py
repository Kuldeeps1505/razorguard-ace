"""Consent Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from razorguard.shared.enums import ConsentMode, ConsentStatus


class ConsentResponse(BaseModel):
    consent_id: uuid.UUID
    intent_id: uuid.UUID
    user_id: uuid.UUID
    mode: ConsentMode
    status: ConsentStatus
    expires_at: datetime
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    reject_reason: str | None = None
    # Returned only while PENDING so the user can approve from the control plane UI.
    consent_token: str | None = None

    model_config = {"from_attributes": True}


class ApproveConsentRequest(BaseModel):
    """User explicitly approves a pending consent."""

    consent_token: str
    intent_id: uuid.UUID


class RejectConsentRequest(BaseModel):
    """User explicitly rejects a pending consent."""

    reason: str | None = None
