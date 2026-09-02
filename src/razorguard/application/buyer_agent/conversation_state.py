"""
Conversation state — in-memory session turns for LLM context window.

SECURITY: This is observability/context only.
Authorization is NEVER derived from conversation history.
Identity, merchant, and price always come from trusted request context or DB.
"""

import sys
from collections import defaultdict

MAX_CONTEXT_TURNS = 20

_SESSION_TURNS: dict[str, list[str]] = defaultdict(list)


def _max_turns() -> int:
    """Read MAX_CONTEXT_TURNS from the module at call time — supports monkeypatching."""
    return sys.modules[__name__].MAX_CONTEXT_TURNS


def append_session_turn(session_id: str, turn: str) -> None:
    """Append a turn, keeping only the most recent MAX_CONTEXT_TURNS turns."""
    turns = _SESSION_TURNS[session_id]
    turns.append(turn)
    limit = _max_turns()
    if len(turns) > limit:
        _SESSION_TURNS[session_id] = turns[-limit:]


def get_session_turns(session_id: str) -> list[str]:
    """Return all turns for a session as a list."""
    return list(_SESSION_TURNS.get(session_id, []))


def build_context_window(session_id: str) -> str:
    """Build the conversation context string for LLM input."""
    turns = get_session_turns(session_id)
    return "\n".join(turns) if turns else ""


def clear_session(session_id: str) -> None:
    """Clear session turns (e.g. on explicit 'Clear chat' action)."""
    _SESSION_TURNS.pop(session_id, None)
