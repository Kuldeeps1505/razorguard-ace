"""
Buyer Agent HTTP route.

POST /agent/chat  — submit natural language, get product recommendations or intent proposal

This is the end-to-end entry point:
  User NL → Buyer Agent → Catalog Search → Intent Proposal → RazorGuard
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.buyer_agent.propose_intent import run_buyer_agent
from razorguard.infrastructure.database.session import get_db_session

router = APIRouter()

# Demo fixed IDs — created by `make seed` / `python scripts/seed_demo.py`
_DEMO_USER_ID     = uuid.UUID("00000000-0000-0000-0000-000000000001")
_DEMO_AGENT_ID    = uuid.UUID("00000000-0000-0000-0000-000000000002")
_DEMO_MERCHANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")


async def get_current_user_id() -> uuid.UUID:
    return _DEMO_USER_ID


async def get_current_agent_id() -> uuid.UUID:
    return _DEMO_AGENT_ID


DBSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[uuid.UUID, Depends(get_current_user_id)]
CurrentAgent = Annotated[uuid.UUID, Depends(get_current_agent_id)]


class AgentChatRequest(BaseModel):
    message: str
    merchant_id: uuid.UUID = _DEMO_MERCHANT_ID  # defaults to active demo merchant
    session_id: str = "default-session"


class AgentChatResponse(BaseModel):
    status: str
    message: str | None = None
    intent: dict | None = None
    upsells: list[dict] = []


@router.post(
    "/chat",
    response_model=AgentChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with the buyer agent",
    description=(
        "Submit natural language to the AI buyer agent. "
        "The agent can search catalogs, compare products, and propose purchase intents. "
        "It CANNOT execute payments — authorization is always deterministic."
    ),
)
async def agent_chat(
    request: AgentChatRequest,
    db: DBSession,
    user_id: CurrentUser,
    agent_id: CurrentAgent,
) -> AgentChatResponse:
    result = await run_buyer_agent(
        user_message=request.message,
        agent_id=agent_id,
        authenticated_user_id=user_id,
        session_id=request.session_id,
        merchant_id=request.merchant_id,
        session=db,
    )
    return AgentChatResponse(
        status=result.get("status", "error"),
        message=result.get("message") or result.get("reason"),
        intent=result.get("intent"),
        upsells=result.get("upsells", []),
    )
