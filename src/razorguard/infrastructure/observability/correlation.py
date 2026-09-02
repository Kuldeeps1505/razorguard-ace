"""
Correlation ID context management.

Every request carries:
  request_id     — unique per HTTP request
  session_id     — user session
  intent_id      — set when an intent is created/loaded
  transaction_id — set when a transaction is created

These flow through logs, metrics, and traces so the full
request_id → intent_id → payment_id → webhook chain is traceable.
"""

from contextvars import ContextVar

import structlog

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_session_id: ContextVar[str] = ContextVar("session_id", default="")
_intent_id: ContextVar[str] = ContextVar("intent_id", default="")
_transaction_id: ContextVar[str] = ContextVar("transaction_id", default="")
_agent_id: ContextVar[str] = ContextVar("agent_id", default="")


def set_request_context(
    request_id: str,
    session_id: str = "",
    intent_id: str = "",
    transaction_id: str = "",
    agent_id: str = "",
) -> None:
    """Bind correlation IDs to the current async context."""
    _request_id.set(request_id)
    _session_id.set(session_id)
    _intent_id.set(intent_id)
    _transaction_id.set(transaction_id)
    _agent_id.set(agent_id)

    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        session_id=session_id or None,
        intent_id=intent_id or None,
        transaction_id=transaction_id or None,
        agent_id=agent_id or None,
    )


def set_intent_id(intent_id: str) -> None:
    _intent_id.set(intent_id)
    structlog.contextvars.bind_contextvars(intent_id=intent_id)


def set_transaction_id(transaction_id: str) -> None:
    _transaction_id.set(transaction_id)
    structlog.contextvars.bind_contextvars(transaction_id=transaction_id)


def get_request_id() -> str:
    return _request_id.get()


def get_correlation_context() -> dict[str, str | None]:
    return {
        "request_id": _request_id.get() or None,
        "session_id": _session_id.get() or None,
        "intent_id": _intent_id.get() or None,
        "transaction_id": _transaction_id.get() or None,
        "agent_id": _agent_id.get() or None,
    }


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()
