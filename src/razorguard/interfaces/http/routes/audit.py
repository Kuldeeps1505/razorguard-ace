"""
Audit trail HTTP routes.

GET /audit/events — recent append-only audit events (control plane UI)
"""

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.audit_event import AuditEvent
from razorguard.infrastructure.database.models.intent import Intent
from razorguard.infrastructure.database.session import get_db_session

router = APIRouter()


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


DBSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[uuid.UUID, Depends(get_current_user_id)]


class AuditEventResponse(BaseModel):
    event_id: uuid.UUID
    request_id: str
    session_id: str | None
    intent_id: uuid.UUID | None
    transaction_id: uuid.UUID | None
    actor: str
    action: str
    result: str
    reason: str | None
    event_hash: str
    previous_hash: str | None
    extra_data: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get(
    "/events",
    response_model=list[AuditEventResponse],
    summary="List recent audit events",
)
async def list_audit_events(
    db: DBSession,
    _user_id: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AuditEventResponse]:
    result = await db.execute(
        select(AuditEvent)
        .where(
            AuditEvent.intent_id.is_(None)
            | AuditEvent.intent_id.in_(select(Intent.id).where(Intent.user_id == _user_id))
        )
        .order_by(AuditEvent.created_at.desc()).limit(limit)
    )
    events = list(result.scalars().all())
    out: list[AuditEventResponse] = []
    for event in events:
        extra = None
        if event.extra_data:
            try:
                extra = json.loads(event.extra_data)
            except json.JSONDecodeError:
                extra = {"raw": event.extra_data}
        out.append(
            AuditEventResponse(
                event_id=event.id,
                request_id=event.request_id,
                session_id=event.session_id,
                intent_id=event.intent_id,
                transaction_id=event.transaction_id,
                actor=event.actor,
                action=event.action,
                result=event.result,
                reason=event.reason,
                event_hash=event.event_hash,
                previous_hash=event.previous_hash,
                extra_data=extra,
                created_at=event.created_at,
            )
        )
    return out
