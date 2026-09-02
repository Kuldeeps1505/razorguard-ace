# ADR 003: Multi-Level Idempotency and Lock Protection

## Status
Accepted

## Context
In automated payment networks, network dropouts, worker crashes, or concurrent agent tool calls can result in duplicate payment submissions, risking double charging the user.

## Decision
We enforce a multi-layered defense to ensure every payment is strictly idempotent:

1. **Distributed Locks**: A distributed lock is acquired in Redis via `redis.asyncio` (`payment_lock:transaction_id`) at the start of payment execution. This prevents parallel workers from processing the same payment intent simultaneously.
2. **Idempotency Keys**: A deterministic idempotency key is generated from the unique transaction/intent hash and passed to the Razorpay API. This guarantees that even if a request is retried against Razorpay's servers due to network issues, it is deduplicated upstream.
3. **Database Constraints**: Database unique indexes prevent duplicate creation of payment attempts and webhook processing records.
4. **Idempotence at Webhooks**: Webhook event processing checks for past processed events in `processed_webhooks` before handling any event.

## Consequences
- Guaranteed single charge: Multiple concurrent triggers result in lock failures (returning `ConcurrentExecutionError`) or get resolved gracefully by upstream deduplication.
- Fault tolerance: In the event of a worker crash, the lock expires automatically (`redis_lock_ttl_seconds`), permitting subsequent recovery attempts.
