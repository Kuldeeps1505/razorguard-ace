"""
Full checkout flow test — from intent creation to Razorpay order.
Verifies the complete pipeline: intent → policy → consent → capability → Razorpay.

Run inside Docker:
  docker compose exec api python /app/scripts/test_checkout_flow.py
"""

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time

sys.path.insert(0, "/app")

BASE_URL = "http://localhost:8000"
PRODUCT_ID = "00000000-0000-0000-0000-000000000102"   # Wireless Mouse ₹1,499
MERCHANT_ID = "00000000-0000-0000-0000-000000000010"
SESSION_ID = f"checkout-test-{int(time.time())}"

import httpx


def step(msg): print(f"\n  ▶  {msg}")
def ok(msg, detail=""): print(f"     ✓  {msg}" + (f"  [{detail}]" if detail else ""))
def fail(msg, detail=""): print(f"     ✗  FAILED: {msg}" + (f"\n        {detail}" if detail else "")); sys.exit(1)


async def main():
    print("\n" + "═"*60)
    print("  RazorGuard — Full Checkout Flow Test")
    print(f"  Session: {SESSION_ID}")
    print("═"*60)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:

        # ── Step 1: Get catalog ────────────────────────────────
        step("1. Fetch canonical product from catalog")
        r = await c.get(f"/merchants/{MERCHANT_ID}/catalog")
        products = {p["product_id"]: p for p in r.json()}
        product = products.get(PRODUCT_ID)
        if not product:
            fail("Product not found", f"Looking for {PRODUCT_ID}\nAvailable: {list(products.keys())}")
        ok(f"Found: {product['title']}", f"₹{product['price_minor']//100}")
        ok("Category", product["category"])

        # ── Step 2: Create intent ──────────────────────────────
        step("2. Create transaction intent")
        r = await c.post("/intents", json={
            "agent_id": "00000000-0000-0000-0000-000000000002",
            "session_id": SESSION_ID,
            "product_id": PRODUCT_ID,
            "merchant_id": MERCHANT_ID,
            "category": product["category"],
            "quantity": 1,
            "amount_minor": product["price_minor"],
            "currency": "INR",
            "payment_method": "UPI",
            "reason": "Checkout test purchase",
        })
        if r.status_code not in (200, 201):
            fail("Intent creation failed", r.text)
        intent = r.json()
        intent_id = intent["intent_id"]
        ok(f"Intent created", intent_id[:8] + "...")
        ok("Amount", f"₹{intent['final_amount_minor']//100}")
        ok("Intent hash", intent["intent_hash"][:16] + "...")
        ok("Status", intent["status"])

        # ── Step 3: Policy simulator preview ──────────────────
        step("3. Policy check preview (simulator)")
        r = await c.post("/policy/simulate", json={
            "amount_minor": intent["final_amount_minor"],
            "currency": "INR",
            "category": product["category"],
            "merchant_id": MERCHANT_ID,
            "product_id": PRODUCT_ID,
            "payment_method": "UPI",
        })
        policy = r.json()
        ok(f"Policy decision: {policy['decision']}", policy["reason"][:50])
        for rule in policy.get("rule_results", []):
            symbol = "✓" if rule["passed"] else "✗"
            print(f"            {symbol}  {rule['rule_name']}")

        # ── Step 4: Full checkout (the real test) ─────────────
        step("4. Full checkout — policy → consent → capability → Razorpay")
        r = await c.post("/payments/checkout", json={"intent_id": intent_id})

        if r.status_code == 403:
            data = r.json()
            fail("Policy denied checkout", data.get("detail", {}).get("reason", ""))

        if r.status_code not in (200, 201):
            fail("Checkout failed", f"HTTP {r.status_code}: {r.text[:300]}")

        result = r.json()
        ok(f"Checkout status: {result['status']}")
        ok("Transaction ID", result["transaction_id"][:8] + "...")

        if result.get("razorpay_order_id"):
            ok("✅ Razorpay order created", result["razorpay_order_id"])
            ok("Policy decision", result.get("policy_decision", ""))
            ok("Capability issued", result.get("capability_id", "")[:8] + "...")
            ok("Amount", f"₹{result.get('amount_minor', 0)//100}")
        elif result["status"] == "unknown":
            ok("⚠️  UNKNOWN state — queued for reconciliation (expected on timeout)")
        else:
            fail("No Razorpay order ID in response", json.dumps(result, indent=2))

        # ── Step 5: Verify transaction status ─────────────────
        step("5. Verify transaction state in DB")
        txn_id = result["transaction_id"]
        r = await c.get(f"/payments/{txn_id}")
        if r.status_code != 200:
            fail("Transaction lookup failed", r.text)
        txn = r.json()
        ok(f"Transaction status: {txn['status']}")
        ok("Razorpay order", txn.get("razorpay_order_id") or "pending webhook")

        # ── Step 6: Simulate webhook ───────────────────────────
        if result.get("razorpay_order_id"):
            step("6. Simulate Razorpay webhook (payment.captured)")
            from razorguard.shared.config import get_settings
            settings = get_settings()

            order_id = result["razorpay_order_id"]
            event_payload = {
                "id": f"evt_test_{int(time.time())}",
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": f"pay_TEST{txn_id[:14].replace('-', '').upper()}",
                            "order_id": order_id,
                            "amount": intent["final_amount_minor"],
                            "currency": "INR",
                            "status": "captured",
                        }
                    }
                },
            }
            body = json.dumps(event_payload).encode()
            secret = settings.razorpay_webhook_secret.encode()
            sig = hmac.new(secret, body, hashlib.sha256).hexdigest()

            r = await c.post(
                "/webhooks/razorpay",
                content=body,
                headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
            )
            wh = r.json()
            ok(f"Webhook processed: {wh.get('status', 'ok')}")

        # ── Summary ───────────────────────────────────────────
        print("\n" + "═"*60)
        print("  ✅ FULL CHECKOUT FLOW COMPLETE")
        print("═"*60)
        print(f"  Intent:       {intent_id}")
        print(f"  Transaction:  {result['transaction_id']}")
        if result.get("razorpay_order_id"):
            print(f"  Razorpay:     {result['razorpay_order_id']}")
            print(f"\n  → Check Razorpay Dashboard → Test Mode → Orders")
            print(f"    Order ID: {result['razorpay_order_id']}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
