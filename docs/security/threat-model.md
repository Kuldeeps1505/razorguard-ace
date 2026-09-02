# Threat Model (Security Domain)

This threat model defines the trust boundaries, entry points, assets, and security mitigations of the RazorGuard ACE control plane.

## Trust Boundaries

- **Boundary 1: LLM Agent Context vs. Backend Engine**: The LLM agent operates in an untrusted environment. It communicates with the backend via tool calls.
- **Boundary 2: Public API vs. Secure Database**: The FastAPI API server validates all requests using JWT authentication before interacting with the database.
- **Boundary 3: External Gateway (Razorpay) Webhooks**: Webhook payloads are received from public networks and are considered untrusted until cryptographically verified.

## Detailed Risk Matrix

### 1. Spoofed Webhook Events
- **Threat**: An attacker sends a forged HTTP POST request to `/webhooks` mimicking a successful Razorpay payment.
- **Mitigation**: Webhook signature verification uses HMAC-SHA256 with the shared secret `RAZORPAY_WEBHOOK_SECRET`. All payloads are checked for a valid signature.
- **Verification**: `test_webhook_system.py::test_invalid_signature_rejected`

### 2. Time-of-Check to Time-of-Use (TOCTOU) Price Drift
- **Threat**: The agent checks the price of a keyboard (e.g. ₹1,500), approves policy, but by the time of execution, the merchant changes the price to ₹5,000.
- **Mitigation**: Immediate catalog price validation runs right before lock acquisition. If the current price differs from the authorized intent price, execution fails closed with `PriceChangedError`.
- **Verification**: `test_chaos_failure.py::test_price_drift_aborts_execution`

### 3. Concurrent Duplicate Requests
- **Threat**: An agent triggers duplicate payment execution calls at the same time to force double charging.
- **Mitigation**: Redis distributed lock is acquired before database execution. Duplicate requests fail to acquire the lock and exit with a concurrency exception.
- **Verification**: `test_chaos_failure.py::test_concurrent_payment_execution_locked`

### 4. Privilege Escalation / Tenant Bypasses
- **Threat**: User A queries the capability or transactions of User B.
- **Mitigation**: Database queries are parameterized and filtered using `user_id` extracted directly from the verified JWT context, never from the request body.
- **Verification**: `test_tenant_isolation.py`
