# ADR 001: Zero-Trust Deterministic Policy Engine

## Status
Accepted

## Context
In agentic commerce systems, LLM agents make decisions on behalf of users (e.g., searching catalogs, recommending items, or preparing purchase requests). However, LLMs are probabilistic, prone to hallucinations, prompt injection attacks, and catalog manipulation. Letting an LLM decide if a payment is authorized introduces critical security risks.

## Decision
We decouple LLM reasoning entirely from payment authorization. The LLM acts solely as a transaction proposer. The actual decision to allow or deny a payment is made by a deterministic, rule-based policy engine running in a secure, non-LLM environment.

Dual-sided validation is enforced:
1. **User Policies**: Evaluates spending limits (per transaction, daily accumulation), category restrictions, time windows, and merchant blocklists/allowlists.
2. **Merchant Policies**: Evaluates if the agent's category is authorized, whether the purchase amount exceeds the merchant's autonomous limit, and if any discount codes correspond to valid campaign rules stored in the database.

Prompt injections in product description/metadata can never bypass policy because all policy evaluation executes deterministically against trusted database records, ignoring freeform fields.

## Consequences
- High security: Hallucinations or adversarial LLM instructions cannot result in unauthorized spending.
- Fail closed: If a policy evaluation fails or is ambiguous, the system denies execution or prompts a human for explicit manual approval.
- High testability: Policies are testable with 100% deterministic unit tests.
