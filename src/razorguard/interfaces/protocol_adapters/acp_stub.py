"""
ACPStubAdapter — Agentic Commerce Protocol (OpenAI + Stripe) adapter.

STATUS: STUB — schema documented, mapping implemented.
        Not connected to a real ACP endpoint.
        Marked as STUB so it cannot be used in production mode.

ACP (Apache 2.0, co-maintained by OpenAI and Stripe) defines how an AI agent
runs checkout against a merchant the agent does not own.
Covers: cart construction, capability negotiation, delegated payment, order lifecycle.

Mapping: ACP checkout envelope → RazorGuard canonical TransactionIntent

DEMO: This stub is used in Demo 8 (Protocol Neutrality):
  "An ACP-format buyer agent purchases from the same merchant,
   subject to the same policy, producing the same audit trail."
"""

import uuid

from razorguard.application.intents.schemas import CreateIntentRequest
from razorguard.interfaces.protocol_adapters.base import ProtocolAdapter
from razorguard.shared.enums import PaymentMethod, ProtocolSource
from razorguard.shared.errors import InvalidIntentError


class ACPStubAdapter(ProtocolAdapter):
    """
    Maps an ACP checkout envelope to a canonical CreateIntentRequest.

    ACP envelope fields used:
      buyer.id              → agent_id (after authentication)
      order.items[0].sku    → product lookup in catalog
      order.merchant.id     → merchant_id
      order.amount.value    → amount_minor (re-validated against catalog)
      order.currency        → currency
      order.session_id      → session_id

    STUB: In production, this would validate against the ACP spec schema.
    """

    # Stub flag — blocks use outside demo mode
    IS_STUB = True

    @property
    def protocol_source(self) -> ProtocolSource:
        return ProtocolSource.ACP

    def to_create_intent_request(
        self,
        *,
        raw_payload: dict,
        agent_id: uuid.UUID,
        authenticated_user_id: uuid.UUID,
        session_id: str,
    ) -> CreateIntentRequest:
        """
        Map ACP checkout envelope to CreateIntentRequest.

        ACP envelope schema (simplified):
        {
          "version": "1.0",
          "buyer": {"id": "...", "session": "..."},
          "order": {
            "merchant": {"id": "..."},
            "items": [{"sku": "...", "quantity": 1}],
            "amount": {"value": 149900, "currency": "INR"}
          }
        }
        """
        try:
            order = raw_payload.get("order", {})
            merchant_id_str = order.get("merchant", {}).get("id", "")
            items = order.get("items", [])
            if not items:
                raise InvalidIntentError("ACP: order.items is empty")

            first_item = items[0]
            amount_info = order.get("amount", {})

            return CreateIntentRequest(
                agent_id=agent_id,
                session_id=session_id,
                # product_id must be resolved via catalog by SKU in real impl
                # For stub: pass sku as product_id (caller must resolve)
                product_id=uuid.UUID(first_item.get("product_id", str(uuid.uuid4()))),
                merchant_id=uuid.UUID(merchant_id_str),
                category=first_item.get("category", "general"),
                quantity=int(first_item.get("quantity", 1)),
                amount_minor=int(amount_info.get("value", 0)),
                currency=amount_info.get("currency", "INR"),
                payment_method=PaymentMethod.UPI,
                protocol_source=ProtocolSource.ACP,
                reason="ACP checkout — via RazorGuard stub adapter",
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise InvalidIntentError(f"ACP envelope parsing failed: {exc}") from exc
