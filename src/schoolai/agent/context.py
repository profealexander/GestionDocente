"""
Context Engine — historial de conversación por sesión (RAM, sin Redis aún).
"""
from __future__ import annotations

from collections import defaultdict

from .schemas import AgentContext

# session_id → list of {role, content}
_store: dict[str, list[dict]] = defaultdict(list)

_MAX_HISTORY = 10  # turnos a conservar por sesión


def load(user_id: str, session_id: str) -> AgentContext:
    return AgentContext(
        user_id=user_id,
        session_id=session_id,
        history=list(_store[session_id]),
    )


def save(ctx: AgentContext, user_text: str, assistant_text: str) -> None:
    history = _store[ctx.session_id]
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_text})
    # Keep only the last N turns
    if len(history) > _MAX_HISTORY * 2:
        _store[ctx.session_id] = history[-(  _MAX_HISTORY * 2):]
