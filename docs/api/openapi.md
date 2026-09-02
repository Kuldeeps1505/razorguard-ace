# API Specification

The control plane exposes HTTP REST API routes for users, merchants, and agents.

## Headers

All responses include the request correlation header:
- `X-Request-ID`: Correlation UUID mapped to the lifecycle of this request.

All authenticated requests require:
- `Authorization: Bearer <JWT_TOKEN>`

---

## 1. Intent Endpoints

### Create Transaction Intent
- **POST** `/intents`
- **Request Body**:
  ```json
  {
    "agent_id": "00000000-0000-0000-0000-000000000002",
    "product_id": "prod_1",
    "merchant_id": "merch_1",
    "amount_minor": 150000,
    "currency": "INR",
    "category": "electronics",
    "quantity": 1,
    "applied_campaign_id": null
  }
  ```
- **Response**:
  ```json
  {
    "intent_id": "uuid-here",
    "status": "CREATED",
    "intent_hash": "sha256-hash-of-canonical-intent-fields",
    "amount_minor": 150000
  }
  ```

---

## 2. Policy Endpoints

### Evaluate Intent Policy
- **POST** `/policy/evaluate`
- **Request Body**:
  ```json
  {
    "intent_id": "uuid-here"
  }
  ```
- **Response**:
  ```json
  {
    "decision": "APPROVE",
    "reason": "All policies satisfied.",
    "evaluated_at": "2026-08-26T14:40:00Z"
  }
  ```

---

## 3. Consent Endpoints

### Request Consent
- **POST** `/consent/request`
- **Request Body**:
  ```json
  {
    "intent_id": "uuid-here"
  }
  ```
- **Response**:
  ```json
  {
    "consent_id": "uuid-here",
    "status": "PENDING"
  }
  ```

---

## 4. Payment Endpoints

### Execute Payment
- **POST** `/payments/execute`
- **Request Body**:
  ```json
  {
    "intent_id": "uuid-here",
    "capability_token": "signed-capability-token-string"
  }
  ```
- **Response**:
  ```json
  {
    "transaction_id": "uuid-here",
    "status": "SUCCESS",
    "razorpay_payment_id": "pay_xyz123"
  }
  ```

---

## 5. Webhook Endpoint

### Razorpay Webhook Event Receiver
- **POST** `/webhooks`
- **Headers**:
  - `X-Razorpay-Signature`: HMAC signature of the request payload
- **Request Body**: Raw JSON from Razorpay
- **Response**: `{"status": "ok"}`
