"""
Protocol ingest HTTP route.

POST /protocols/{protocol}/intents

Accepts a native / ACP / AP2 / unknown envelope and translates it
to a canonical TransactionIntent. Authorization is identical for all.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.buyer_agent.ingest_protocol import ingest_protocol_intent
from razorguard.application.intents.schemas import IntentResponse
from razorguard.infrastructure.database.session import get_db_session

router = APIRouter()


async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


async def get_current_agent_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000002")


DBSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[uuid.UUID, Depends(get_current_user_id)]
CurrentAgent = Annotated[uuid.UUID, Depends(get_current_agent_id)]


class ProtocolIngestRequest(BaseModel):
    envelope: dict[str, Any]
    session_id: str = Field(default="default-session", min_length=1, max_length=64)


@router.post(
    "/{protocol}/intents",
    response_model=IntentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a buyer-protocol envelope as a canonical intent",
    description=(
        "Translate ACP / AP2 / native / unknown envelopes into a TransactionIntent. "
        "protocol_source is observability only. Stubs are blocked in production."
    ),
)
async def ingest_protocol_route(
    protocol: str,
    request: ProtocolIngestRequest,
    db: DBSession,
    user_id: CurrentUser,
    agent_id: CurrentAgent,
) -> IntentResponse:
    return await ingest_protocol_intent(
        protocol=protocol,
        raw_payload=request.envelope,
        agent_id=agent_id,
        authenticated_user_id=user_id,
        session_id=request.session_id,
        session=db,
    )
