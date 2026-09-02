import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from razorguard.infrastructure.database.models.merchant import Merchant, MerchantPolicy
from razorguard.infrastructure.database.models.catalog_product import CatalogProduct
from razorguard.shared.config import get_settings
from razorguard.shared.enums import MerchantStatus, ProductAvailability

async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    merchant_id = uuid.UUID("00000000-0000-0000-0000-000000000010")

    async with async_session() as session:
        # Check if merchant exists
        merchant = await session.get(Merchant, merchant_id)
        if not merchant:
            merchant = Merchant(
                id=merchant_id,
                name="Demo Electronics",
                display_name="Demo Electronics",
                status=MerchantStatus.ACTIVE
            )
            session.add(merchant)
            policy = MerchantPolicy(
                merchant_id=merchant_id,
                agent_commerce_enabled=True,
                max_autonomous_order_minor=10000000,
                max_discount_pct=10,
                max_agent_txns_per_day=100,
            )
            session.add(policy)
            
            # Add products
            headphones = CatalogProduct(
                id=uuid.uuid4(),
                merchant_id=merchant_id,
                sku="WH-1000XM4-DEMO",
                title="Premium Wireless Noise Cancelling Headphones",
                description="Industry leading noise cancellation, up to 30 hours of battery life.",
                category="electronics",
                price_minor=299900, # 2999 INR
                currency="INR",
                availability=ProductAvailability.IN_STOCK,
                agent_purchase_allowed=True,
            )
            session.add(headphones)

            earbuds = CatalogProduct(
                id=uuid.uuid4(),
                merchant_id=merchant_id,
                sku="EP-100",
                title="Budget Wireless Earbuds",
                description="Cheap wireless earbuds with 10h battery.",
                category="electronics",
                price_minor=150000, # 1500 INR
                currency="INR",
                availability=ProductAvailability.IN_STOCK,
                agent_purchase_allowed=True,
            )
            session.add(earbuds)

            await session.commit()
            print("Successfully seeded merchant 00000000-0000-0000-0000-000000000010 with products.")
        else:
            print("Merchant already exists. Seeding products if empty.")
            
            # check products
            from sqlalchemy import select
            result = await session.execute(select(CatalogProduct).where(CatalogProduct.merchant_id == merchant_id))
            products = result.scalars().all()
            if not products:
                headphones = CatalogProduct(
                    id=uuid.uuid4(),
                    merchant_id=merchant_id,
                    sku="WH-1000XM4-DEMO",
                    title="Premium Wireless Noise Cancelling Headphones",
                    description="Industry leading noise cancellation, up to 30 hours of battery life.",
                    category="electronics",
                    price_minor=299900,
                    currency="INR",
                    availability=ProductAvailability.IN_STOCK,
                    agent_purchase_allowed=True,
                )
                session.add(headphones)

                earbuds = CatalogProduct(
                    id=uuid.uuid4(),
                    merchant_id=merchant_id,
                    sku="EP-100",
                    title="Budget Wireless Earbuds",
                    description="Cheap wireless earbuds with 10h battery.",
                    category="electronics",
                    price_minor=150000,
                    currency="INR",
                    availability=ProductAvailability.IN_STOCK,
                    agent_purchase_allowed=True,
                )
                session.add(earbuds)
                await session.commit()
                print("Seeded products for existing merchant.")
            else:
                print("Products already exist.")
            
if __name__ == "__main__":
    asyncio.run(main())
