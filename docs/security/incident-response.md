# Incident Response Procedures

Operational guidelines for managing security incidents or emergency events within the RazorGuard ACE control plane.

## 1. Webhook Signature Key Compromise
If the `RAZORPAY_WEBHOOK_SECRET` is compromised:
1. Generate a new secret in the Razorpay Dashboard.
2. Update the `RAZORPAY_WEBHOOK_SECRET` environment variable in the control plane deployment (.env or container configuration).
3. Restart the API server containers to reload the settings.
4. Old webhook signatures will fail verification immediately, preventing attackers from injecting forged payment outcomes.

## 2. Capability Signing Key Rotation
If `CAPABILITY_SIGNING_KEY` needs to be rotated:
1. Generate a new random 32-byte hex string.
2. Update the `CAPABILITY_SIGNING_KEY` environment variable.
3. Restart the API server.
4. Note: Outstanding capabilities issued under the old key will fail verification immediately. Agents must request re-authorization (creating a new intent/capability) to proceed with payment.

## 3. Merchant Master Kill Switch Activation
If a merchant notices suspicious agent behavior or catalog anomalies, they can activate the emergency Kill Switch:
1. Toggle the `agent_commerce_enabled` field to `false` in the Merchant Policy (via the Merchant Dashboard or by executing a direct PATCH request to `/merchants/policy`).
2. The control plane immediately rejects any new capability requests or payment executions for this merchant.
3. Database queries for authorization check this status in real-time, bypassing any local caching.

## 4. Rate-Limit Attack Mitigations
If the API is subjected to brute-force or denial-of-service attempts:
1. Redis sliding window metrics will detect the surge.
2. IP addresses exceeding the limit are blocked automatically for 60 seconds (standard rate limit window).
3. Under extreme scenarios, the rate limit thresholds (e.g. `RATE_LIMIT_API_PER_MINUTE`) can be lowered via environment variables without requiring code changes.
