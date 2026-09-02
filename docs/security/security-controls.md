# Security Controls

This document details the cryptographic, database, and rate limiting controls built into RazorGuard ACE.

## Cryptographic Protections

### 1. Capability Signing
- Capability tokens are signed using HMAC-SHA256.
- The signing key (`CAPABILITY_SIGNING_KEY`) is stored securely as an environment variable and is verified on every payment attempt.

### 2. Webhook Signature Verification
- Inbound webhooks from Razorpay require validation.
- The HTTP header `X-Razorpay-Signature` is computed using HMAC-SHA256 with `RAZORPAY_WEBHOOK_SECRET` over the raw request payload.
- Payload parsing only occurs after signature verification succeeds.

### 3. Password Hashing
- If database credentials or local merchant profiles require passwords, standard bcrypt hashing is applied (plain text passwords are never stored).

## Database Isolation & Auditing

### 1. Row-Level Tenant Isolation
- Every database query for policies, intents, and transactions includes an explicit filter matching the authenticated `user_id`.
- Client requests cannot override or bypass this filter.

### 2. Immutable Audit Logs
- Every transaction state transition creates a permanent `AuditEvent` record.
- Audit logs contain the correlation ID, event type, actor (user or agent), policy details, and timestamp.
- Audit records are write-once (updates are disabled at the repository layer).

## Network & Rate Limiting Controls

### 1. Redis Sliding Window Rate Limiter
- Implemented using a Lua script in Redis.
- Enforces requests-per-minute thresholds for general API calls (100/min), payment attempts (10/min), and agent operations (60/min).
- Scope is identified by User ID or Client IP.

### 2. Secrets Redaction
- Log processor `_redact_sensitive` (using `structlog`) automatically redacts keys, passwords, and secrets from all system logs.
- Preconfigured list of redacted fields includes `api_key`, `secret`, `razorpay_key_secret`, and `jwt_secret_key`.
