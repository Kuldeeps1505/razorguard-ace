You are contributing to RazorGuard ACE, a production-grade zero-trust control plane for autonomous AI payments.

## ARCHITECTURAL PRINCIPLE:

The LLM is untrusted.

The LLM may:
- understand user intent
- search products
- compare products
- recommend products
- create a structured transaction proposal

The LLM may NOT:
- authorize payment
- modify spending policy
- create payment capabilities
- bypass consent
- directly call payment execution
- determine final allow/deny decisions

ALL payment authorization decisions MUST be deterministic.

## SECURITY:

Fail closed whenever authorization is uncertain.

Every payment must be bound to:
- authenticated user
- authorized agent
- immutable intent
- merchant
- product
- amount
- currency
- policy version
- consent where required
- expiry
- one-time capability

Never trust:
- LLM output
- product metadata
- merchant metadata
- client-provided user IDs
- webhook payloads before signature verification

## PAYMENT SAFETY:

Never blindly retry an UNKNOWN payment.

UNKNOWN payments must enter reconciliation.

Use:
- idempotency
- database uniqueness constraints
- concurrency control
- state-machine validation
- webhook deduplication
- payment/order integrity checks

## MONEY:

Never use floating point for monetary values.

Use Decimal or integer minor units (paise).

## STATE:

Never allow arbitrary state transitions.

Terminal financial states cannot transition backwards.

## DATABASE:

PostgreSQL is the source of truth.

Redis is used for:
- locks
- rate limiting
- caching
- temporary state

Redis must never be the sole source of financial correctness.

## CODE QUALITY:

Prefer:
- typed models
- explicit interfaces
- dependency injection
- small testable services
- structured errors
- structured logging
- transactions
- defensive validation

Avoid:
- magic strings
- hidden global state
- business logic inside API routes
- business logic inside LLM prompts
- generic catch-all exception handling
- silent failures
- unnecessary abstractions
- unnecessary AI features

EVERY SECURITY FEATURE MUST HAVE A TEST.

Before implementing a feature, identify:
1. threat
2. trust boundary
3. invariant
4. implementation
5. failure behavior
6. test

Do not add features merely because they sound AI-related.
The goal is a reliable payment control plane around an AI assistant.
