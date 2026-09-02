"""
AP2StubAdapter — Agent Payments Protocol (Google → FIDO Alliance) adapter.

STATUS: STUB — schema documented, mapping implemented.
        Marked as STUB so it cannot be used in production mode.

AP2 is a payment-agnostic framework for authorizing agent-led payments.
Uses cryptographically signed payment mandates.
Supports traditional card payments and crypto via x402 extension.
Donated to FIDO Alliance on 28 April 2026.

Mapping: AP2 signed mandate → RazorGuard canonical TransactionIntent

The authorization still goes through RazorGuard's full control plane —
AP2 is just the entry format, not the authorization mechanism.
"""

import uuid

from razorguard.application.intents.schemas import CreateIntentRequest
from razorguard.interfaces.protocol_adapters.base import ProtocolAdapter
from razorguard.shared.enums import PaymentMethod, ProtocolSource
from razorguard.shared.errors import InvalidIntentError


class AP2StubAdapter(ProtocolAdapter):
    """
    Maps an AP2 signed mandate to a canonical CreateIntentRequest.

    AP2 mandate fields used:
      mandate.agent_id           → agent_id (after authentication)
      mandate.merchant.id        → merchant_id
      mandate.purchase.product   → product_id
      mandate.purchase.amount    → amount_minor
      mandate.purchase.currency  → currency
      mandate.session            → session_id

    STUB: In production, this would verify the AP2 cryptographic signature
    using the FIDO Alliance verifier before accepting the mandate.
    """

    IS_STUB = True

    @property
    def protocol_source(self) -> ProtocolSource:
        return ProtocolSource.AP2

    def to_create_intent_request(
        self,
        *,
        raw_payload: dict,
        agent_id: uuid.UUID,
        authenticated_user_id: uuid.UUID,
        session_id: str,
    ) -> CreateIntentRequest:
        """
        Map AP2 mandate to CreateIntentRequest.

        AP2 mandate schema (simplified):
        {
          "version": "1.0",
          "mandate": {
            "merchant": {"id": "..."},
            "purchase": {
              "product_id": "...",
              "category": "electronics",
              "quantity": 1,
              "amount": 149900,
              "currency": "INR"
            },
            "session": "...",
            "signature": "..."  <- verified by AP2 verifier in production
          }
        }
        """
        try:
            mandate = raw_payload.get("mandate", {})
            merchant_id_str = mandate.get("merchant", {}).get("id", "")
            purchase = mandate.get("purchase", {})

            return CreateIntentRequest(
                agent_id=agent_id,
                session_id=mandate.get("session", session_id),
                product_id=uuid.UUID(purchase.get("product_id", str(uuid.uuid4()))),
                merchant_id=uuid.UUID(merchant_id_str),
                category=purchase.get("category", "general"),
                quantity=int(purchase.get("quantity", 1)),
                amount_minor=int(purchase.get("amount", 0)),
                currency=purchase.get("currency", "INR"),
                payment_method=PaymentMethod.UPI,
                protocol_source=ProtocolSource.AP2,
                reason="AP2 mandate — via RazorGuard stub adapter",
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise InvalidIntentError(f"AP2 mandate parsing failed: {exc}") from exc
