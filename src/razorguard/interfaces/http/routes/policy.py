"""
Policy HTTP routes.

POST /policy/simulate   — simulate policy decision (no side effects, demo feature)
POST /policy/evaluate   — evaluate policy for an existing intent

The simulator is the key demo feature that makes the policy engine visible.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.policy.evaluate_policy import (
    simulate_policy_for_request,
)
from razorguard.application.policy.schemas import PolicyDecisionResponse, PolicySimulateRequest
from razorguard.infrastructure.database.session import get_db_session

router = APIRouter()


# Placeholder — replaced with JWT auth in Phase 5
async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


DBSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[uuid.UUID, Depends(get_current_user_id)]


@router.post(
    "/simulate",
    response_model=PolicyDecisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Simulate a policy decision (demo feature — no side effects)",
    description=(
        "Run any hypothetical transaction through the policy engine. "
        "Returns the full decision with every rule result. "
        "Nothing is persisted. Safe to call repeatedly for demos."
    ),
)
async def simulate_policy_route(
    request: PolicySimulateRequest,
    db: DBSession,
    user_id: CurrentUser,
) -> PolicyDecisionResponse:
    return await simulate_policy_for_request(
        request=request,
        authenticated_user_id=user_id,
        session=db,
    )
