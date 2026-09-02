"""
Ingest a buyer-protocol envelope and create a canonical TransactionIntent.

Flow:
  External envelope → ProtocolAdapter → CreateIntentRequest → create_intent()

The control plane never sees the original envelope. Authorization is
identical regardless of protocol_source.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.intents.create_intent import create_intent
from razorguard.application.intents.schemas import IntentResponse
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.interfaces.protocol_adapters.registry import get_adapter, parse_protocol_source

logger = get_logger(__name__)


async def ingest_protocol_intent(
    *,
    protocol: str,
    raw_payload: dict[str, Any],
    agent_id: uuid.UUID,
    authenticated_user_id: uuid.UUID,
    session_id: str,
    session: AsyncSession,
    allow_stubs: bool | None = None,
) -> IntentResponse:
    source = parse_protocol_source(protocol)
    adapter = get_adapter(source, allow_stubs=allow_stubs)

    request = adapter.to_create_intent_request(
        raw_payload=raw_payload,
        agent_id=agent_id,
        authenticated_user_id=authenticated_user_id,
        session_id=session_id,
    )

    logger.info(
        "protocol_envelope_ingested",
        protocol=source.value,
        adapter=adapter.__class__.__name__,
        user_id=str(authenticated_user_id),
    )

    return await create_intent(
        request=request,
        authenticated_user_id=authenticated_user_id,
        session=session,
    )
