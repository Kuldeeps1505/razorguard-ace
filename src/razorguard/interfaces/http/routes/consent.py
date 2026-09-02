"""Consent HTTP routes."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.consent.approve_consent import approve_consent
from razorguard.application.consent.reject_consent import reject_consent
from razorguard.application.consent.request_consent import request_consent
from razorguard.application.consent.schemas import (
    ApproveConsentRequest,
    ConsentResponse,
    RejectConsentRequest,
)
from razorguard.infrastructure.database.session import get_db_session

router = APIRouter()


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


DBSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[uuid.UUID, Depends(get_current_user_id)]


class CreateMandateRequest(BaseModel):
    agent_id: uuid.UUID
    merchant_id: uuid.UUID
    max_amount_per_txn_minor: int = Field(gt=0)
    max_daily_amount_minor: int = Field(gt=0)
    allowed_categories: list[str] = []
    valid_until: datetime


@router.get(
    "/consents/pending",
    response_model=list[ConsentResponse],
    summary="List pending consents for the authenticated user",
)
async def list_pending_consents(
    db: DBSession,
    user_id: CurrentUser,
) -> list[ConsentResponse]:
    from sqlalchemy import select

    from razorguard.application.consent.request_consent import _to_response
    from razorguard.infrastructure.database.models.consent import Consent
    from razorguard.shared.enums import ConsentStatus

    result = await db.execute(
        select(Consent).where(
            Consent.user_id == user_id,
            Consent.status == ConsentStatus.PENDING,
        )
    )
    return [_to_response(c) for c in result.scalars().all()]


@router.post(
    "/intents/{intent_id}/consent",
    response_model=ConsentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request user consent for an intent",
)
async def request_consent_route(
    intent_id: uuid.UUID,
    db: DBSession,
    user_id: CurrentUser,
) -> ConsentResponse:
    return await request_consent(
        intent_id=intent_id,
        authenticated_user_id=user_id,
        session=db,
    )


@router.post(
    "/consents/{consent_id}/approve",
    response_model=ConsentResponse,
    summary="Approve a pending consent",
)
async def approve_consent_route(
    consent_id: uuid.UUID,
    request: ApproveConsentRequest,
    db: DBSession,
    user_id: CurrentUser,
) -> ConsentResponse:
    """
    Approve a pending consent.

    The client can now call the synchronous checkout endpoint to resume the
    pipeline and receive the payment outcome in that response.
    """
    return await approve_consent(
        consent_id=consent_id,
        intent_id=request.intent_id,
        consent_token=request.consent_token,
        authenticated_user_id=user_id,
        session=db,
    )


@router.post(
    "/consents/{consent_id}/reject",
    response_model=ConsentResponse,
    summary="Reject a pending consent",
)
async def reject_consent_route(
    consent_id: uuid.UUID,
    request: RejectConsentRequest,
    db: DBSession,
    user_id: CurrentUser,
) -> ConsentResponse:
    return await reject_consent(
        consent_id=consent_id,
        authenticated_user_id=user_id,
        reason=request.reason,
        session=db,
    )


@router.post("/mandates", summary="Create a bounded delegated-payment mandate")
async def create_mandate_route(request: CreateMandateRequest, db: DBSession, user_id: CurrentUser) -> dict:
    from razorguard.application.consent.mandates import create_mandate
    mandate = await create_mandate(
        user_id=user_id,
        agent_id=request.agent_id,
        merchant_id=request.merchant_id,
        max_amount_per_txn_minor=request.max_amount_per_txn_minor,
        max_daily_amount_minor=request.max_daily_amount_minor,
        allowed_categories=request.allowed_categories,
        valid_until=request.valid_until,
        session=db,
    )
    return {"mandate_id": str(mandate.id), "status": mandate.status, "valid_until": mandate.valid_until}


@router.post("/mandates/{mandate_id}/revoke", summary="Immediately revoke a delegated-payment mandate")
async def revoke_mandate_route(mandate_id: uuid.UUID, db: DBSession, user_id: CurrentUser) -> dict:
    from razorguard.application.consent.mandates import revoke_mandate
    mandate = await revoke_mandate(mandate_id=mandate_id, user_id=user_id, session=db)
    return {"mandate_id": str(mandate.id), "status": mandate.status, "revoked_at": mandate.revoked_at}


@router.get("/intents/{intent_id}/approval-receipt", summary="Get the canonical approval receipt and checkout diff")
async def approval_receipt(intent_id: uuid.UUID, db: DBSession, user_id: CurrentUser) -> dict:
    import json

    from sqlalchemy import select

    from razorguard.infrastructure.database.models.commerce_controls import CheckoutQuote
    from razorguard.infrastructure.database.repositories.intent_repository import IntentRepository
    intent = await IntentRepository(db).get_by_id_for_user(intent_id, user_id)
    if not intent:
        return {"status": "not_found"}
    quote = await db.scalar(select(CheckoutQuote).where(CheckoutQuote.intent_id == intent_id))
    if not quote:
        return {"status": "quote_not_created"}
    canonical = json.loads(quote.canonical_payload)
    return {
        "status": quote.status,
        "quote_hash": quote.quote_hash,
        "expires_at": quote.expires_at,
        "canonical_checkout": canonical,
        "diff": {
            "agent_proposed_amount_minor": intent.amount_minor,
            "canonical_final_amount_minor": intent.final_amount_minor,
            "discount_minor": intent.discount_minor,
            "changed_after_discovery": False,
        },
    }
