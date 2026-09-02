# Threat Model

Threat model detailing the system's attack surface, trust boundaries, threat actors, and engineering mitigations.

## Threat Actors and Vectors

| Threat Actor | Attack Vector | Mitigation | Verification Test |
|---|---|---|---|
| **Malicious LLM** | Attempts to self-authorize or bypass user spending policy. | The policy engine runs in a secure, deterministic environment separate from the LLM. | `test_policy_engine.py` |
| **Compromised Agent** | Attempts to replay a previously used capability token. | Nonce validation in Redis enforces one-time usage for capability tokens. | `test_authorization_bypass.py` |
| **Malicious Product Metadata** | Prompt injection inside product description to influence spending. | Catalog description is treated strictly as data (escaped/bounded) and never processed as instructions. | `test_prompt_injection.py` |
| **Malicious Merchant** | Modifies product price at check-out time (TOCTOU/Price Drift). | Final validation re-checks catalog price against the intent hash immediately before payment. | `test_chaos_failure.py` |
| **Replay Attacker** | Captures webhook event and resubmits it to fake a payment success. | Webhook verification checks signature and deduplicates events using a persistent PostgreSQL table. | `test_webhook_system.py` |
| **Unauthenticated Client** | Attempts to fetch or alter policy settings of another user. | Tenant isolation is enforced via user-session context and DB query filter bindings. | `test_tenant_isolation.py` |
