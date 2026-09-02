"""
Intent HTTP routes.

POST   /intents        — create a new transaction intent
GET    /intents        — list recent intents
GET    /intents/{id}   — get intent by ID (scoped to authenticated user)
GET    /intents/{id}/status — lightweight status check
DELETE /intents/{id}   — cancel a specific intent
DELETE /intents        — cancel all non-terminal intents for the user

SECURITY:
- user_id is ALWAYS derived from JWT, never from request body
- All responses are scoped to the authenticated user
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.intents.create_intent import _to_response, create_intent
from razorguard.application.intents.schemas import (
    CreateIntentRequest,
    IntentResponse,
    IntentStatusResponse,
)
from razorguard.infrastructure.database.models.intent import Intent as IntentModel
from razorguard.infrastructure.database.repositories.intent_repository import IntentRepository
from razorguard.infrastructure.database.session import get_db_session
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.shared.clock import is_expired
from razorguard.shared.enums import TransactionStatus
from razorguard.shared.errors import IntentExpiredError

router = APIRouter()
logger = get_logger(__name__)


# Placeholder dependency — replaced with real JWT auth in Phase 5
async def get_current_user_id() -> uuid.UUID:
    """Stub: returns a fixed UUID. Replaced by JWT middleware in Phase 5."""
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


DBSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[uuid.UUID, Depends(get_current_user_id)]


@router.get(
    "",
    response_model=list[IntentResponse],
    summary="List recent intents for the authenticated user",
)
async def list_intents(
    db: DBSession,
    user_id: CurrentUser,
) -> list[IntentResponse]:
    repo = IntentRepository(db)
    intents = await repo.list_recent_for_user(user_id)
    return [_to_response(intent) for intent in intents]


@router.post(
    "",
    response_model=IntentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a transaction intent",
)
async def create_intent_route(
    request: CreateIntentRequest,
    db: DBSession,
    user_id: CurrentUser,
) -> IntentResponse:
    return await create_intent(
        request=request,
        authenticated_user_id=user_id,
        session=db,
    )


@router.get(
    "/{intent_id}",
    response_model=IntentResponse,
    summary="Get intent by ID",
)
async def get_intent(
    intent_id: uuid.UUID,
    db: DBSession,
    user_id: CurrentUser,
) -> IntentResponse:
    repo = IntentRepository(db)
    intent = await repo.get_by_id_for_user(intent_id, user_id)
    if not intent:
        raise IntentExpiredError(str(intent_id))
    return _to_response(intent)


@router.get(
    "/{intent_id}/status",
    response_model=IntentStatusResponse,
    summary="Get intent lifecycle status",
)
async def get_intent_status(
    intent_id: uuid.UUID,
    db: DBSession,
    user_id: CurrentUser,
) -> IntentStatusResponse:
    repo = IntentRepository(db)
    intent = await repo.get_by_id_for_user(intent_id, user_id)
    if not intent:
        raise IntentExpiredError(str(intent_id))
    status_enum = TransactionStatus(intent.status)
    return IntentStatusResponse(
        intent_id=intent.id,
        status=status_enum,
        is_expired=is_expired(intent.expires_at),
        is_terminal=status_enum.is_terminal,
    )


@router.delete(
    "",
    status_code=status.HTTP_200_OK,
    summary="Cancel all non-terminal intents for the authenticated user",
)
async def cancel_all_intents(
    db: DBSession,
    user_id: CurrentUser,
) -> dict:
    """Mark every non-terminal intent as CANCELLED so the UI starts fresh."""
    _TERMINAL = [
        TransactionStatus.COMPLETED,
        TransactionStatus.FAILED,
        TransactionStatus.POLICY_BLOCKED,
        TransactionStatus.CONSENT_REJECTED,
        TransactionStatus.EXPIRED,
        TransactionStatus.CANCELLED,
        TransactionStatus.AGENT_STOPPED,
    ]
    result = await db.execute(
        update(IntentModel)
        .where(
            IntentModel.user_id == user_id,
            IntentModel.status.notin_([s.value for s in _TERMINAL]),
        )
        .values(status=TransactionStatus.CANCELLED.value)
    )
    await db.commit()
    count = result.rowcount
    logger.info("intents_bulk_cancelled", user_id=str(user_id), count=count)
    return {"cancelled": count}


@router.delete(
    "/{intent_id}",
    status_code=status.HTTP_200_OK,
    summary="Cancel a specific intent",
)
async def cancel_intent(
    intent_id: uuid.UUID,
    db: DBSession,
    user_id: CurrentUser,
) -> dict:
    """Cancel a single intent regardless of its current state (except COMPLETED)."""
    repo = IntentRepository(db)
    intent = await repo.get_by_id_for_user(intent_id, user_id)
    if not intent:
        raise IntentExpiredError(str(intent_id))

    # Don't allow cancellation of already-completed transactions
    if intent.status == TransactionStatus.COMPLETED:
        return {"cancelled": 0, "reason": "Intent already COMPLETED"}

    await db.execute(
        update(IntentModel)
        .where(IntentModel.id == intent_id, IntentModel.user_id == user_id)
        .values(status=TransactionStatus.CANCELLED.value)
    )
    await db.commit()
    logger.info("intent_cancelled", intent_id=str(intent_id), user_id=str(user_id))
    return {"cancelled": 1, "intent_id": str(intent_id)}
