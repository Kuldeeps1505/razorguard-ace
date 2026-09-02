"""
BuyerAgent — the LLM-powered shopping agent entry point.

This is the ONLY component that calls the LLM.
All other components are deterministic.

Flow:
  User NL → LLM → tool calls → catalog data → propose_intent
                                                      ↓
                                              RazorGuard control plane
                                              (never the LLM)

SECURITY:
  - LLM output is ALWAYS untrusted
  - Tool arguments are schema-validated before use
  - propose_intent → creates a TransactionIntent in DB
  - LLM never calls execute_payment, issue_capability, or approve_consent
  - Catalog content is wrapped as external data before LLM context
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from razorguard.application.buyer_agent.conversation_state import (
    append_session_turn,
    build_context_window,
)
from razorguard.application.buyer_agent.upsell import get_complementary_products
from razorguard.application.intents.create_intent import create_intent
from razorguard.application.intents.schemas import CreateIntentRequest
from razorguard.infrastructure.llm.client import call_llm
from razorguard.infrastructure.llm.prompt_injection_guard import sanitize_catalog_product_for_llm
from razorguard.infrastructure.llm.schemas import BUYER_AGENT_TOOLS, build_system_prompt
from razorguard.infrastructure.observability.logging import get_logger
from razorguard.infrastructure.observability.metrics import agent_tool_calls
from razorguard.shared.enums import PaymentMethod, ProtocolSource
from razorguard.shared.errors import InvalidIntentError

FORBIDDEN_TOOLS = frozenset({"execute_payment", "issue_capability", "approve_consent"})

logger = get_logger(__name__)

MAX_AGENT_ITERATIONS = 10  # prevent infinite loops


async def run_buyer_agent(
    *,
    user_message: str,
    agent_id: uuid.UUID,
    authenticated_user_id: uuid.UUID,
    session_id: str,
    merchant_id: uuid.UUID,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Run the buyer agent for one user message.

    Returns either:
      - {"status": "proposed", "intent": IntentResponse} — intent created
      - {"status": "response", "message": str} — LLM responded without purchase
      - {"status": "error", "reason": str} — something went wrong
    """
    logger.info(
        "buyer_agent_started",
        agent_id=str(agent_id),
        user_id=str(authenticated_user_id),
        session_id=session_id,
    )
    # Session log is observability + LLM context only — never authorization.
    append_session_turn(session_id, f"user: {user_message}")

    # Conversation context is advisory only. Identity, merchant binding, price,
    # and authorization still come from trusted request/DB data below.
    messages_context = build_context_window(session_id)
    iteration = 0

    while iteration < MAX_AGENT_ITERATIONS:
        iteration += 1

        # Call LLM with buyer agent tools and merchant-aware system prompt
        llm_response = await call_llm(
            system_prompt=build_system_prompt(str(merchant_id)),
            user_message=messages_context,
            tools=BUYER_AGENT_TOOLS,
        )

        tool_calls = llm_response.get("tool_calls", [])

        # No tool calls — LLM responded with text
        if not tool_calls:
            content = (llm_response.get("content") or "").strip()
            if not content:
                logger.warning("buyer_agent_empty_model_response", agent_id=str(agent_id))
                response = {
                    "status": "error",
                    "reason": "The buyer agent returned no purchase action or response. Please try again.",
                }
                append_session_turn(session_id, f"assistant: {response['reason']}")
                return response
            response = {
                "status": "response",
                "message": content,
            }
            append_session_turn(session_id, f"assistant: {response['message']}")
            return response

        # Process tool calls
        tool_results = []
        for tc in tool_calls:
            tool_name = tc["tool_name"]
            tool_input = tc["tool_input"]

            agent_tool_calls.labels(tool_name=tool_name).inc()
            logger.info("buyer_agent_tool_call", tool=tool_name, agent_id=str(agent_id))

            result = await _execute_tool(
                tool_name=tool_name,
                tool_input=tool_input,
                agent_id=agent_id,
                authenticated_user_id=authenticated_user_id,
                session_id=session_id,
                merchant_id=merchant_id,
                session=session,
            )

            # If propose_intent succeeded, return immediately
            if tool_name == "propose_intent" and result.get("status") == "proposed":
                intent = result["intent"]
                result["upsells"] = await get_complementary_products(
                    purchased_product_id=uuid.UUID(str(intent["product_id"])),
                    merchant_id=merchant_id,
                    session=session,
                )
                append_session_turn(
                    session_id,
                    f"assistant: Purchase intent proposed for product {intent['product_id']}.",
                )
                return result

            tool_results.append(f"Tool '{tool_name}' result: {result}")

        # Add tool results to context for next iteration
        messages_context = f"{messages_context}\n\n" + "\n".join(tool_results)

    logger.warning("buyer_agent_max_iterations", agent_id=str(agent_id))
    response = {"status": "error", "reason": "max_iterations_exceeded"}
    append_session_turn(session_id, "assistant: Unable to complete this request safely.")
    return response


async def _execute_tool(
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    agent_id: uuid.UUID,
    authenticated_user_id: uuid.UUID,
    session_id: str,
    merchant_id: uuid.UUID,
    session: AsyncSession,
) -> dict[str, Any]:
    """Execute a validated tool call. Tool arguments are schema-validated here."""

    if tool_name in FORBIDDEN_TOOLS:
        logger.warning("buyer_agent_forbidden_tool", tool=tool_name)
        return {"error": "tool_not_permitted", "tool": tool_name}

    if tool_name == "search_catalog":
        return await _tool_search_catalog(
            tool_input=tool_input,
            merchant_id=merchant_id,
            session=session,
        )

    if tool_name == "compare_products":
        return await _tool_compare_products(
            tool_input=tool_input,
            session=session,
        )

    if tool_name == "propose_intent":
        return await _tool_propose_intent(
            tool_input=tool_input,
            agent_id=agent_id,
            authenticated_user_id=authenticated_user_id,
            session_id=session_id,
            merchant_id=merchant_id,
            session=session,
        )

    logger.warning("buyer_agent_unknown_tool", tool=tool_name)
    return {"error": f"Unknown tool: {tool_name}"}


async def _tool_search_catalog(
    *,
    tool_input: dict,
    merchant_id: uuid.UUID,
    session: AsyncSession,
) -> dict:
    """READ tool — returns catalog products, sanitized for LLM."""
    from razorguard.infrastructure.database.repositories.catalog_repository import CatalogRepository
    from sqlalchemy import select, or_
    from razorguard.infrastructure.database.models.catalog_product import CatalogProduct
    from razorguard.shared.enums import ProductAvailability

    category = tool_input.get("category")
    max_price = tool_input.get("max_price_minor")
    query_text = (tool_input.get("query") or "").lower().strip()

    # Base query — all agent-purchasable, in-stock products for this merchant
    stmt = select(CatalogProduct).where(
        CatalogProduct.merchant_id == merchant_id,
        CatalogProduct.availability == ProductAvailability.IN_STOCK,
        CatalogProduct.agent_purchase_allowed.is_(True),
    )

    # Only filter by category if it's a single clean value that might match
    # Don't filter on compound values like "electronics & audio" — do text search instead
    clean_category = (category or "").strip().lower()
    VALID_CATEGORIES = {"electronics", "audio", "accessories", "books", "groceries", "footwear", "fashion"}
    if clean_category and clean_category in VALID_CATEGORIES:
        stmt = stmt.where(CatalogProduct.category == clean_category)

    if max_price:
        stmt = stmt.where(CatalogProduct.price_minor <= max_price)

    result = await session.execute(stmt)
    products = list(result.scalars().all())

    # If query text provided, filter by title/description match
    if query_text and products:
        keywords = query_text.split()
        filtered = []
        for p in products:
            searchable = f"{p.title} {p.description or ''} {p.category}".lower()
            if any(kw in searchable for kw in keywords):
                filtered.append(p)
        # If no keyword match, return all (don't return empty if LLM searched broadly)
        if filtered:
            products = filtered

    # Sanitize each product — wrap description as external data
    results = []
    for p in products[:10]:  # limit to 10 results
        safe_product = sanitize_catalog_product_for_llm(
            sku=p.sku,
            title=p.title,
            description=p.description,
            category=p.category,
            price_minor=p.price_minor,
            currency=p.currency,
        )
        results.append({
            "product_id": str(p.id),
            "merchant_id": str(p.merchant_id),
            "display": safe_product,
        })

    return {"products": results, "count": len(results)}


async def _tool_compare_products(
    *,
    tool_input: dict,
    session: AsyncSession,
) -> dict:
    """READ tool — compare multiple products."""
    from sqlalchemy import select

    from razorguard.infrastructure.database.models.catalog_product import CatalogProduct

    product_ids_raw = tool_input.get("product_ids", [])
    if not product_ids_raw or len(product_ids_raw) > 5:
        return {"error": "Provide 2-5 product IDs to compare"}

    comparisons = []
    for pid_str in product_ids_raw:
        try:
            pid = uuid.UUID(pid_str)
        except ValueError:
            continue
        result = await session.execute(select(CatalogProduct).where(CatalogProduct.id == pid))
        p = result.scalar_one_or_none()
        if p:
            comparisons.append(
                {
                    "product_id": str(p.id),
                    "title": p.title,
                    "category": p.category,
                    "price_minor": p.price_minor,
                    "currency": p.currency,
                    "available": p.availability == "IN_STOCK",
                }
            )

    return {"comparisons": comparisons}


async def _tool_propose_intent(
    *,
    tool_input: dict,
    agent_id: uuid.UUID,
    authenticated_user_id: uuid.UUID,
    session_id: str,
    session: AsyncSession,
    merchant_id: uuid.UUID | None = None,
) -> dict:
    """
    CONTROLLED tool — creates a TransactionIntent.

    Validates tool arguments before creating intent.
    user_id comes from authenticated_user_id, NEVER from tool_input.
    """
    # Schema validation of tool arguments
    product_id_str = tool_input.get("product_id")
    if not product_id_str:
        return {"error": "product_id is required"}

    try:
        product_id = uuid.UUID(product_id_str)
    except ValueError as exc:
        raise InvalidIntentError("Invalid product_id format") from exc

    # The merchant is request-scoped trusted context, not an LLM-controlled
    # argument. The fallback maintains direct unit-test compatibility only.
    if merchant_id is None:
        try:
            merchant_id = uuid.UUID(tool_input["merchant_id"])
        except (KeyError, ValueError) as exc:
            raise InvalidIntentError("Invalid merchant_id format") from exc

    # Fetch canonical price from catalog (never trust LLM-suggested price)
    from razorguard.infrastructure.database.repositories.catalog_repository import CatalogRepository

    catalog_repo = CatalogRepository(session)
    product = await catalog_repo.get_available_for_agent(
        product_id=product_id,
        merchant_id=merchant_id,
    )
    if not product:
        return {"error": "Product not available for agent purchase"}

    quantity = max(1, int(tool_input.get("quantity", 1)))
    # LLM-suggested amount is ignored — catalog price is canonical.
    canonical_amount = product.price_minor * quantity

    request = CreateIntentRequest(
        agent_id=agent_id,
        session_id=session_id,
        product_id=product_id,
        merchant_id=merchant_id,
        category=product.category,
        quantity=quantity,
        amount_minor=canonical_amount,
        currency=product.currency,
        payment_method=PaymentMethod.UPI,
        campaign_code=tool_input.get("campaign_code"),
        reason=tool_input.get("reason"),
        protocol_source=ProtocolSource.RAZORGUARD,
    )

    intent = await create_intent(
        request=request,
        authenticated_user_id=authenticated_user_id,
        session=session,
    )

    logger.info(
        "buyer_agent_intent_proposed",
        intent_id=str(intent.intent_id),
        product_id=product_id_str,
        amount=canonical_amount,
    )

    return {"status": "proposed", "intent": intent.model_dump()}
