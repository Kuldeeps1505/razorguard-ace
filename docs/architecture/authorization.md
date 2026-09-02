# Authorization Model & Policy Engine

All authorizations in RazorGuard are subject to zero-trust principles. No LLM decision is authoritative.

## Dual-Sided Policy Engine

Every transaction is evaluated against both the User's spending policy and the Merchant's commerce policy.

```
                  Intent Submitted
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
   User Policy                     Merchant Policy
   - Max Amount?                   - Agent Commerce Enabled?
   - Daily Spent?                  - Max Autonomous Order?
   - Category Allowed?             - Valid Campaign/Discount?
   - Merchant Allowed?             - Allowed Payment Method?
        │                                 │
        └────────────────┬────────────────┘
                         ▼
                     Both Pass?
                   ┌─────┴─────┐
                  YES          NO
                   │           │
                   ▼           ▼
               APPROVE      DENY / ASK_USER
```

### User Policy Engine
Ensures the user retains complete control over what their agents spend. If a policy rules out a transaction, the engine returns `DENY` or `ASK_USER` (requiring explicit human consent).

### Merchant Policy Engine
Ensures merchants are protected against misbehaving or compromised agents. Key protections:
- **Kill Switch**: The merchant can disable agent commerce entirely (`agent_commerce_enabled = false`), which immediately blocks all incoming agent transactions.
- **Autonomous Limits**: Sets a threshold above which a human must approve the transaction.
- **Campaign Verification**: Verifies that applied coupons come from active, valid campaigns configured in the database, preventing agents from inventing discounts.

## Cryptographic Capabilities

Once a policy engine approves a transaction (and the user grants consent if required), the Control Plane issues a **Capability Token**.

- **Structure**: Encodes intent ID, amount, currency, policy version, user/agent identifiers, nonce, and expiry time.
- **Security**: Signed with a server-side signing key using HMAC-SHA256.
- **One-time Use**: The nonce is stored in Redis upon usage. Any replay attempt is blocked.
- **Version Pinning**: If a policy changes after capability issuance, the version mismatch invalidates the token during payment execution.
