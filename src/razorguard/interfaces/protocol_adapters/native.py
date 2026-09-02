"""
NativeAdapter — RazorGuard's own protocol (fully implemented).

The native format is the CreateIntentRequest schema itself.
This adapter is a passthrough with validation.
"""

import uuid

from razorguard.application.intents.schemas import CreateIntentRequest
from razorguard.interfaces.protocol_adapters.base import ProtocolAdapter
from razorguard.shared.enums import ProtocolSource


class NativeAdapter(ProtocolAdapter):
    """
    RazorGuard native protocol adapter.
    The payload IS already a CreateIntentRequest-compatible dict.
    """

    IS_STUB = False

    @property
    def protocol_source(self) -> ProtocolSource:
        return ProtocolSource.RAZORGUARD

    def to_create_intent_request(
        self,
        *,
        raw_payload: dict,
        agent_id: uuid.UUID,
        authenticated_user_id: uuid.UUID,
        session_id: str,
    ) -> CreateIntentRequest:
        payload = {**raw_payload}
        payload["agent_id"] = str(agent_id)
        payload["session_id"] = session_id
        payload["protocol_source"] = ProtocolSource.RAZORGUARD
        return CreateIntentRequest(**payload)
