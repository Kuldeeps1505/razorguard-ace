"""
ProtocolAdapter base class.

Any external agentic commerce protocol can be adapted to
RazorGuard's canonical TransactionIntent format.

Design principle:
  External Buyer Protocol (ACP / AP2 / UAP / native)
          ↓
  ProtocolAdapter.to_create_intent_request()
          ↓
  Canonical CreateIntentRequest
          ↓
  RazorGuard Control Plane (authorization is IDENTICAL regardless of source)

Adding a new buyer protocol = implement one ProtocolAdapter subclass.
Nothing else in the authorization chain changes.

The protocol_source field is stored for observability only.
No security decision is based on which protocol was used.
"""

import uuid
from abc import ABC, abstractmethod

from razorguard.application.intents.schemas import CreateIntentRequest
from razorguard.shared.enums import ProtocolSource


class ProtocolAdapter(ABC):
    """Base class for all protocol adapters."""

    @property
    @abstractmethod
    def protocol_source(self) -> ProtocolSource:
        """Which protocol this adapter handles."""

    @abstractmethod
    def to_create_intent_request(
        self,
        *,
        raw_payload: dict,
        agent_id: uuid.UUID,
        authenticated_user_id: uuid.UUID,
        session_id: str,
    ) -> CreateIntentRequest:
        """
        Convert a protocol-specific payload to a canonical CreateIntentRequest.

        The canonical request is what the control plane operates on.
        The protocol_source is recorded for audit only.
        """
