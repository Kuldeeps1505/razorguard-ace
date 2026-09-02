# ADR 002: Signed Capability Tokens for Delegated Authorization

## Status
Accepted

## Context
When a transaction is approved by the policy engine (or manually by the user), the agent needs an authorization proof to execute the payment via Razorpay. Simply passing an intent ID is vulnerable to interception, tampering, replay attacks, and state bypass (e.g. executing payments without going through policy evaluation).

## Decision
We implement a "Capability-Based Security" model. When a payment intent is approved, the control plane issues a cryptographically signed, short-lived, one-time-use **Capability Token**.

The Capability Token:
1. Encodes and binds:
   - `intent_id` (immutable transaction intent reference)
   - `user_id` & `agent_id`
   - `amount_minor` (paise) & `currency`
   - `policy_version` (prevents reuse if policy gets changed)
   - `nonce` (prevents replay attacks)
   - `expires_at` (short TTL, e.g. 5 minutes)
2. Is signed using HMAC-SHA256 with a key stored strictly in the control plane's secure environment.
3. Is verified immediately before payment submission.

## Consequences
- No tampered payments: Since the payload is signed, any alteration in the amount, merchant, or intent ID invalidates the token.
- No replay attacks: Nonce uniqueness checks (via Redis) prevent reuse of a token.
- Short validity window: Expiry bounds the risk window.
- Fail closed: If signature verification fails, the capability is rejected, and payment execution fails closed.
