"""
Phase 14 — Capability authorization bypass attempts.

Wrong user, wrong agent, expired, revoked, replayed capabilities
must never authorize payment.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from razorguard.application.authorization.consume_capability import consume_capability
from razorguard.shared.enums import CapabilityStatus
from razorguard.shared.errors import (
    CapabilityExpiredError,
    CapabilityInvalidError,
    CapabilityReplayError,
    CapabilityRevokedError,
)

USER = uuid.UUID("00000000-0000-0000-0000-000000000001")
AGENT = uuid.UUID("00000000-0000-0000-0000-000000000002")
INTENT = uuid.UUID("00000000-0000-0000-0000-000000000003")
CAP_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def _cap(**overrides) -> MagicMock:
    cap = MagicMock()
    cap.id = CAP_ID
    cap.status = CapabilityStatus.ACTIVE
    cap.user_id = USER
    cap.agent_id = AGENT
    cap.intent_id = INTENT
    cap.merchant_id = uuid.uuid4()
    cap.product_id = uuid.uuid4()
    cap.amount_minor = 149900
    cap.currency = "INR"
    cap.intent_hash = "hash"
    cap.nonce = "nonce"
    cap.session_id = "sess"
    cap.expires_at = datetime.now(UTC) + timedelta(minutes=5)
    cap.policy_version_id = uuid.uuid4()
    cap.merchant_policy_id = uuid.uuid4()
    cap.signature = "sig"
    cap.used_by_request_id = None
    for key, value in overrides.items():
        setattr(cap, key, value)
    return cap


def _repo(cap: MagicMock) -> MagicMock:
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=cap)
    repo.save = AsyncMock()
    return repo


@pytest.fixture
def consume_patches():
    with (
        patch(
            "razorguard.application.authorization.consume_capability.verify_capability_signature",
            return_value=True,
        ),
        patch(
            "razorguard.application.authorization.consume_capability.get_settings",
        ) as settings,
    ):
        settings.return_value.capability_signing_key = "test-cap-key-16ch"
        yield


@pytest.mark.asyncio
async def test_wrong_user_rejected(consume_patches):
    cap = _cap()
    with patch(
        "razorguard.application.authorization.consume_capability.CapabilityRepository",
        return_value=_repo(cap),
    ):
        with pytest.raises(CapabilityInvalidError, match="user"):
            await consume_capability(
                capability_id=CAP_ID,
                authenticated_user_id=uuid.uuid4(),
                authenticated_agent_id=AGENT,
                intent_id=INTENT,
                request_id="r1",
                session=MagicMock(),
            )


@pytest.mark.asyncio
async def test_wrong_agent_rejected(consume_patches):
    cap = _cap()
    with patch(
        "razorguard.application.authorization.consume_capability.CapabilityRepository",
        return_value=_repo(cap),
    ):
        with pytest.raises(CapabilityInvalidError, match="agent"):
            await consume_capability(
                capability_id=CAP_ID,
                authenticated_user_id=USER,
                authenticated_agent_id=uuid.uuid4(),
                intent_id=INTENT,
                request_id="r1",
                session=MagicMock(),
            )


@pytest.mark.asyncio
async def test_expired_capability_rejected(consume_patches):
    cap = _cap(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    with patch(
        "razorguard.application.authorization.consume_capability.CapabilityRepository",
        return_value=_repo(cap),
    ):
        with pytest.raises(CapabilityExpiredError):
            await consume_capability(
                capability_id=CAP_ID,
                authenticated_user_id=USER,
                authenticated_agent_id=AGENT,
                intent_id=INTENT,
                request_id="r1",
                session=MagicMock(),
            )


@pytest.mark.asyncio
async def test_revoked_capability_rejected(consume_patches):
    cap = _cap(status=CapabilityStatus.REVOKED)
    with patch(
        "razorguard.application.authorization.consume_capability.CapabilityRepository",
        return_value=_repo(cap),
    ):
        with pytest.raises(CapabilityRevokedError):
            await consume_capability(
                capability_id=CAP_ID,
                authenticated_user_id=USER,
                authenticated_agent_id=AGENT,
                intent_id=INTENT,
                request_id="r1",
                session=MagicMock(),
            )


@pytest.mark.asyncio
async def test_capability_replay_rejected(consume_patches):
    cap = _cap(status=CapabilityStatus.USED, used_by_request_id="first")
    with patch(
        "razorguard.application.authorization.consume_capability.CapabilityRepository",
        return_value=_repo(cap),
    ):
        with pytest.raises(CapabilityReplayError):
            await consume_capability(
                capability_id=CAP_ID,
                authenticated_user_id=USER,
                authenticated_agent_id=AGENT,
                intent_id=INTENT,
                request_id="replay",
                session=MagicMock(),
            )


@pytest.mark.asyncio
async def test_tampered_signature_rejected(consume_patches):
    cap = _cap()
    with (
        patch(
            "razorguard.application.authorization.consume_capability.CapabilityRepository",
            return_value=_repo(cap),
        ),
        patch(
            "razorguard.application.authorization.consume_capability.verify_capability_signature",
            return_value=False,
        ),
    ):
        with pytest.raises(CapabilityInvalidError, match="tamper"):
            await consume_capability(
                capability_id=CAP_ID,
                authenticated_user_id=USER,
                authenticated_agent_id=AGENT,
                intent_id=INTENT,
                request_id="r1",
                session=MagicMock(),
            )


@pytest.mark.asyncio
async def test_missing_capability_rejected(consume_patches):
    repo = _repo(_cap())
    repo.get_by_id = AsyncMock(return_value=None)
    with patch(
        "razorguard.application.authorization.consume_capability.CapabilityRepository",
        return_value=repo,
    ):
        with pytest.raises(CapabilityInvalidError, match="not found"):
            await consume_capability(
                capability_id=CAP_ID,
                authenticated_user_id=USER,
                authenticated_agent_id=AGENT,
                intent_id=INTENT,
                request_id="r1",
                session=MagicMock(),
            )
