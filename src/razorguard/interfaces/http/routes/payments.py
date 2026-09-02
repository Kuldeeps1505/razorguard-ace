"""
Payment HTTP routes.

POST /payments/checkout         — full pipeline: intent → policy → consent → capability → Razorpay
POST /payments/execute          — execute with an existing capability token
GET  /payments/{transaction_id} — get transaction status
"""

import uuid
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.infrastructure.cache.redis import get_redis
from razorguard.infrastructure.database.session import get_db_session
from razorguard.infrastructure.observability.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

# ── Demo fixed IDs (replaced by JWT in production) ───────────
_DEMO_USER_ID  = uuid.UUID("00000000-0000-0000-0000-000000000001")
_DEMO_AGENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


async def get_current_user_id() -> uuid.UUID:
    return _DEMO_USER_ID


async def get_current_agent_id() -> uuid.UUID:
    return _DEMO_AGENT_ID


DBSession    = Annotated[AsyncSession, Depends(get_db_session)]
RedisClient  = Annotated[aioredis.Redis, Depends(get_redis)]  # type: ignore[type-arg]
CurrentUser  = Annotated[uuid.UUID, Depends(get_current_user_id)]
CurrentAgent = Annotated[uuid.UUID, Depends(get_current_agent_id)]


# ── Schemas ───────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    """One-call full pipeline: policy → consent → capability → Razorpay order."""
    intent_id: uuid.UUID


class ExecutePaymentRequest(BaseModel):
    """Execute with an already-issued capability token."""
    intent_id: uuid.UUID
    capability_id: uuid.UUID
    session_id: str = "default-session"


class PaymentResponse(BaseModel):
    # A consent-gated checkout has not created a transaction yet.
    transaction_id: str | None = None
    status: str
    razorpay_order_id: str | None = None
    policy_decision: str | None = None
    capability_id: str | None = None
    amount_minor: int | None = None


# ── Routes ────────────────────────────────────────────────────

@router.post(
    "/checkout",
    response_model=PaymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Full checkout — policy → consent → capability → Razorpay order",
    description=(
        "Orchestrates the complete authorization pipeline for an existing intent. "
        "Policy evaluated, consent handled, capability issued, Razorpay order created. "
        "This is what the frontend 'Approve & Pay' button calls."
    ),
)
async def checkout(
    request: CheckoutRequest,
    db: DBSession,
    redis: RedisClient,
    user_id: CurrentUser,
    agent_id: CurrentAgent,
) -> PaymentResponse:
    from razorguard.application.payments.checkout_handoff import checkout_and_pay
    from razorguard.infrastructure.observability.correlation import get_request_id

    # Keep the complete authorization and payment pipeline in the request so
    # the caller receives its real outcome.  Celery remains available for
    # reconciliation and other background maintenance, but checkout itself
    # must not depend on a queue worker for the demo flow to make progress.
    result = await checkout_and_pay(
        intent_id=request.intent_id,
        authenticated_user_id=user_id,
        authenticated_agent_id=agent_id,
        request_id=get_request_id(),
        session_id="checkout-session",
        session=db,
        redis=redis,
    )
    return PaymentResponse(**result)


@router.post(
    "/execute",
    response_model=PaymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute with an existing capability token",
)
async def execute_payment_route(
    request: ExecutePaymentRequest,
    db: DBSession,
    redis: RedisClient,
    user_id: CurrentUser,
    agent_id: CurrentAgent,
) -> PaymentResponse:
    from razorguard.application.payments.execute_payment import execute_payment
    from razorguard.infrastructure.observability.correlation import get_request_id

    result = await execute_payment(
        intent_id=request.intent_id,
        capability_id=request.capability_id,
        authenticated_user_id=user_id,
        authenticated_agent_id=agent_id,
        request_id=get_request_id(),
        session_id=request.session_id,
        session=db,
        redis=redis,
    )
    return PaymentResponse(**result)


@router.get(
    "/{transaction_id}",
    response_model=PaymentResponse,
    summary="Get transaction status",
)
async def get_transaction(
    transaction_id: uuid.UUID,
    db: DBSession,
    user_id: CurrentUser,
) -> PaymentResponse:
    from sqlalchemy import select

    from razorguard.infrastructure.database.models.transaction import Transaction
    from razorguard.shared.errors import RazorGuardError

    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise RazorGuardError(
            message=f"Transaction {transaction_id} not found",
            code="TRANSACTION_NOT_FOUND",
        )
    return PaymentResponse(
        transaction_id=str(txn.id),
        status=txn.status,
        razorpay_order_id=txn.razorpay_order_id,
    )
