# ADR 004: Explicit Payment State Machine and Reconciliation

## Status
Accepted

## Context
When executing a payment via external gateways (like Razorpay), network timeouts can leave the payment in an unknown state. Blindly retrying could result in double-spending, while ignoring it leaves the transaction status incomplete.

## Decision
We enforce a strict, unidirectional payment state machine:

1. **Unidirectional Transitions**: Transactions move from `CREATED` → `VALIDATING` → `POLICY_APPROVED` → `FINAL_VALIDATION` → `EXECUTION_LOCKED` → `PAYMENT_SUBMITTED` → `SUCCESS` or `FAILED`.
2. **Terminal Invariance**: Once a transaction reaches a terminal state (`SUCCESS`, `FAILED`), it is locked and can never transition back or change.
3. **Reconciliation for `UNKNOWN`**: If a submission times out or returns an ambiguous response, the transaction transitions to `UNKNOWN`. It is blocked from any further local payment attempts.
4. **Celery Worker Reconciler**: A background worker periodically queries Razorpay using read-only API calls (`fetch_payments_for_order`). It transitions the payment from `UNKNOWN` → `VERIFYING` and finally resolves it to `COMPLETED` or `FAILED` based on the API response.

## Consequences
- Never blind retry: No payment in `UNKNOWN` is retried locally.
- Safe closed state: Active locks and status checks prevent race conditions during background reconciliation.
- Complete audit trail: All state changes are recorded in the audit logs.
