"""
Demo seed script — creates the minimum data needed for the demo.

Creates:
  - 1 demo user (ID: 00000000-0000-0000-0000-000000000001)
  - 1 demo agent (ID: 00000000-0000-0000-0000-000000000002)
  - 1 demo merchant (ID: 00000000-0000-0000-0000-000000000010)
  - 1 merchant policy (agent commerce enabled)
  - 1 active delegation (user → agent)
  - Sample catalog products
  - 1 spending policy for the demo user

Run: python scripts/seed_demo.py
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, UTC, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Fixed IDs — must match the stub dependencies in route files
DEMO_USER_ID    = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEMO_AGENT_ID   = uuid.UUID("00000000-0000-0000-0000-000000000002")
DEMO_MERCHANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")


async def main() -> None:
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("LOG_FORMAT", "console")
    os.environ.setdefault("LOG_LEVEL", "WARNING")

    from razorguard.shared.config import get_settings
    from razorguard.infrastructure.database.session import get_session_factory
    from razorguard.shared.security import hash_secret, generate_id

    settings = get_settings()
    factory = get_session_factory(settings)

    async with factory() as session:
        await _seed_all(session)
        await session.commit()

    print("✓ Demo seed complete.")
    print(f"  User ID:     {DEMO_USER_ID}")
    print(f"  Agent ID:    {DEMO_AGENT_ID}")
    print(f"  Merchant ID: {DEMO_MERCHANT_ID}")


async def _seed_all(session) -> None:
    from sqlalchemy import select, text
    from razorguard.shared.security import hash_secret, generate_id

    # ── User ─────────────────────────────────────────────────
    from razorguard.infrastructure.database.models.user import User
    existing_user = await session.get(User, DEMO_USER_ID)
    if not existing_user:
        user = User(
            id=DEMO_USER_ID,
            email="demo@razorguard.dev",
            hashed_password=hash_secret("demo-password-not-real"),
            full_name="Demo User",
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        print("  + Created demo user")
    else:
        print("  ~ Demo user already exists")

    await session.flush()

    # ── Merchant ──────────────────────────────────────────────
    from razorguard.infrastructure.database.models.merchant import Merchant, MerchantPolicy
    existing_merchant = await session.get(Merchant, DEMO_MERCHANT_ID)
    if not existing_merchant:
        merchant = Merchant(
            id=DEMO_MERCHANT_ID,
            name="demo_store",
            display_name="RazorGuard Demo Store",
            status="ACTIVE",
        )
        session.add(merchant)
        await session.flush()

        policy = MerchantPolicy(
            id=uuid.UUID(generate_id()),
            merchant_id=DEMO_MERCHANT_ID,
            version=1,
            agent_commerce_enabled=True,
            max_autonomous_order_minor=1_000_000,  # ₹10,000
            max_discount_pct=15,
            max_agent_txns_per_day=100,
            allowed_agent_categories=json.dumps(["electronics", "audio", "accessories"]),
            allowed_payment_methods=json.dumps(["UPI", "CARD"]),
            refund_requires_human=True,
            is_current=True,
        )
        session.add(policy)
        print("  + Created demo merchant + policy")
    else:
        print("  ~ Demo merchant already exists")

    await session.flush()

    # ── Agent ─────────────────────────────────────────────────
    from razorguard.infrastructure.database.models.agent import Agent
    existing_agent = await session.get(Agent, DEMO_AGENT_ID)
    if not existing_agent:
        agent = Agent(
            id=DEMO_AGENT_ID,
            user_id=DEMO_USER_ID,
            name="RazorGuard Shopping Agent",
            description="Demo AI buyer agent",
            credential_hash=hash_secret("demo-agent-credential"),
            status="ACTIVE",
            allowed_tools=json.dumps(["SEARCH", "COMPARE", "PROPOSE_PURCHASE"]),
            max_payment_attempts_per_hour=10,
            max_tool_calls_per_minute=60,
        )
        session.add(agent)
        print("  + Created demo agent")
    else:
        print("  ~ Demo agent already exists")

    await session.flush()

    # ── Delegation ────────────────────────────────────────────
    from razorguard.infrastructure.database.models.delegation import Delegation
    from sqlalchemy import select as sa_select
    result = await session.execute(
        sa_select(Delegation).where(
            Delegation.user_id == DEMO_USER_ID,
            Delegation.agent_id == DEMO_AGENT_ID,
            Delegation.status == "ACTIVE",
        )
    )
    existing_delegation = result.scalar_one_or_none()
    if not existing_delegation:
        now = datetime.now(UTC)
        delegation = Delegation(
            id=uuid.UUID(generate_id()),
            user_id=DEMO_USER_ID,
            agent_id=DEMO_AGENT_ID,
            status="ACTIVE",
            max_transaction_minor=500_000,    # ₹5,000
            max_daily_spend_minor=2_000_000,  # ₹20,000
            max_monthly_spend_minor=0,
            require_consent_above_minor=200_000,  # ₹2,000
            allowed_categories=json.dumps(["electronics", "audio", "accessories"]),
            allowed_merchant_ids=json.dumps([str(DEMO_MERCHANT_ID)]),
            blocked_merchant_ids=json.dumps([]),
            allowed_currencies=json.dumps(["INR"]),
            valid_from=now,
            valid_until=now + timedelta(days=365),
        )
        session.add(delegation)
        print("  + Created demo delegation")
    else:
        print("  ~ Demo delegation already exists")

    await session.flush()

    # ── Spending policy ───────────────────────────────────────
    from razorguard.infrastructure.database.models.spending_policy import SpendingPolicy, PolicyVersion
    from razorguard.shared.security import compute_intent_hash
    result2 = await session.execute(
        sa_select(SpendingPolicy).where(SpendingPolicy.user_id == DEMO_USER_ID)
    )
    existing_policy = result2.scalar_one_or_none()
    if not existing_policy:
        policy_id = uuid.UUID(generate_id())
        sp = SpendingPolicy(
            id=policy_id,
            user_id=DEMO_USER_ID,
            name="Demo Spending Policy",
            is_active=True,
        )
        session.add(sp)
        await session.flush()

        rules_hash = compute_intent_hash(
            "500000", "2000000", "0", "200000", "[]", "[]", "[]", '["INR"]'
        )
        pv = PolicyVersion(
            id=uuid.UUID(generate_id()),
            policy_id=policy_id,
            version=1,
            is_current=True,
            max_single_transaction_minor=500_000,
            daily_limit_minor=2_000_000,
            monthly_limit_minor=0,
            require_consent_above_minor=200_000,
            allowed_categories=json.dumps([]),
            allowed_merchant_ids=json.dumps([]),
            blocked_merchant_ids=json.dumps([]),
            allowed_payment_methods=json.dumps(["UPI", "CARD"]),
            allowed_currencies=json.dumps(["INR"]),
            rules_hash=rules_hash,
        )
        session.add(pv)
        print("  + Created demo spending policy")
    else:
        print("  ~ Demo spending policy already exists")

    await session.flush()

    # ── Catalog products ──────────────────────────────────────
    from razorguard.infrastructure.database.models.catalog_product import CatalogProduct
    result3 = await session.execute(
        sa_select(CatalogProduct).where(CatalogProduct.merchant_id == DEMO_MERCHANT_ID)
    )
    products = result3.scalars().all()
    if not products:
        demo_products = [
            {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000101"),
                "sku": "WH-1000XM4-DEMO",
                "title": "Premium Wireless Noise-Cancelling Headphones",
                "description": "Industry-leading noise cancellation, up to 30h battery life, premium build quality.",
                "category": "audio",
                "price_minor": 299900,   # ₹2,999
                "currency": "INR",
                "availability": "IN_STOCK",
                "agent_purchase_allowed": True,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000102"),
                "sku": "MX-MASTER3-DEMO",
                "title": "Ergonomic Wireless Mouse",
                "description": "Advanced ergonomic design, 70-day battery, precision scrolling.",
                "category": "electronics",
                "price_minor": 149900,   # ₹1,499
                "currency": "INR",
                "availability": "IN_STOCK",
                "agent_purchase_allowed": True,
                "upsell_product_ids": json.dumps(["00000000-0000-0000-0000-000000000103"]),
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000103"),
                "sku": "KB-K380-DEMO",
                "title": "Compact Multi-Device Keyboard",
                "description": "Bluetooth keyboard, connects up to 3 devices, quiet keys.",
                "category": "electronics",
                "price_minor": 249900,   # ₹2,499
                "currency": "INR",
                "availability": "IN_STOCK",
                "agent_purchase_allowed": True,
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000104"),
                "sku": "USB-HUB-DEMO",
                "title": "USB-C 7-Port Hub",
                "description": "Connect all your peripherals with 7-in-1 USB-C hub.",
                "category": "accessories",
                "price_minor": 199900,   # ₹1,999
                "currency": "INR",
                "availability": "IN_STOCK",
                "agent_purchase_allowed": True,
            },
        ]
        for p in demo_products:
            product = CatalogProduct(
                id=p["id"],
                merchant_id=DEMO_MERCHANT_ID,
                sku=p["sku"],
                title=p["title"],
                description=p["description"],
                category=p["category"],
                price_minor=p["price_minor"],
                currency=p["currency"],
                availability=p["availability"],
                agent_purchase_allowed=p["agent_purchase_allowed"],
                eligible_campaign_ids=json.dumps([]),
                upsell_product_ids=p.get("upsell_product_ids", json.dumps([])),
            )
            session.add(product)
        print(f"  + Created {len(demo_products)} demo catalog products")
    else:
        print(f"  ~ {len(products)} catalog products already exist")


if __name__ == "__main__":
    asyncio.run(main())
