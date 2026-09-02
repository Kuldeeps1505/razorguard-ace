"""Tamper-evident, transactionally persisted audit events."""

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.database.models.audit_event import AuditEvent
from razorguard.shared.enums import AuditActor
from razorguard.shared.security import generate_id


async def record_audit_event(
    *, session: AsyncSession, request_id: str, actor: AuditActor, action: str,
    result: str, reason: str | None = None, session_id: str | None = None,
    intent_id: uuid.UUID | None = None, transaction_id: uuid.UUID | None = None,
    capability_id: uuid.UUID | None = None, actor_id: str | None = None,
    policy_version_id: uuid.UUID | None = None, extra_data: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one event to a serialized hash chain in the caller's DB transaction."""
    # PostgreSQL transaction advisory lock prevents concurrent writers from
    # creating competing heads of the global evidence chain.
    await session.execute(text("SELECT pg_advisory_xact_lock(824192)"))
    previous = await session.scalar(
        select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1)
    )
    previous_hash = previous.event_hash if previous else None
    payload = {
        "request_id": request_id, "session_id": session_id,
        "intent_id": str(intent_id) if intent_id else None,
        "transaction_id": str(transaction_id) if transaction_id else None,
        "capability_id": str(capability_id) if capability_id else None,
        "actor": actor.value, "actor_id": actor_id,
        "action": action, "result": result,
        "reason": reason,
        "policy_version_id": str(policy_version_id) if policy_version_id else None,
        "extra_data": extra_data or {}, "previous_hash": previous_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    event = AuditEvent(
        id=uuid.UUID(generate_id()),
        request_id=request_id,
        session_id=session_id,
        intent_id=intent_id,
        transaction_id=transaction_id,
        capability_id=capability_id,
        actor=actor,
        actor_id=actor_id,
        action=action,
        result=result,
        reason=reason,
        policy_version_id=policy_version_id,
        previous_hash=previous_hash,
        event_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        extra_data=json.dumps(extra_data, sort_keys=True, default=str) if extra_data else None,
    )
    session.add(event)
    await session.flush()
    return event
