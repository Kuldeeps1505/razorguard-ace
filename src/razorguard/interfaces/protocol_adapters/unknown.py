"""
UnknownProtocolAdapter — last-resort mapping for unrecognized envelopes.

STATUS: fully implemented (not a stub).
protocol_source is UNKNOWN for observability only.
Authorization still runs on the canonical CreateIntentRequest.
"""

import uuid

from razorguard.application.intents.schemas import CreateIntentRequest
from razorguard.interfaces.protocol_adapters.base import ProtocolAdapter
from razorguard.shared.enums import PaymentMethod, ProtocolSource
from razorguard.shared.errors import InvalidIntentError


class UnknownProtocolAdapter(ProtocolAdapter):
    """Extract canonical fields from an unrecognized envelope, then fail closed if incomplete."""

    IS_STUB = False

    @property
    def protocol_source(self) -> ProtocolSource:
        return ProtocolSource.UNKNOWN

    def to_create_intent_request(
        self,
        *,
        raw_payload: dict,
        agent_id: uuid.UUID,
        authenticated_user_id: uuid.UUID,
        session_id: str,
    ) -> CreateIntentRequest:
        try:
            product_id = raw_payload.get("product_id")
            merchant_id = raw_payload.get("merchant_id")
            if not product_id or not merchant_id:
                raise InvalidIntentError(
                    "UNKNOWN protocol: product_id and merchant_id are required"
                )
            return CreateIntentRequest(
                agent_id=agent_id,
                session_id=session_id,
                product_id=uuid.UUID(str(product_id)),
                merchant_id=uuid.UUID(str(merchant_id)),
                category=str(raw_payload.get("category") or "general"),
                quantity=int(raw_payload.get("quantity") or 1),
                amount_minor=int(raw_payload["amount_minor"]),
                currency=str(raw_payload.get("currency") or "INR"),
                payment_method=PaymentMethod.UPI,
                protocol_source=ProtocolSource.UNKNOWN,
                reason="Ingested via unknown protocol adapter",
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise InvalidIntentError(f"UNKNOWN protocol envelope parsing failed: {exc}") from exc
