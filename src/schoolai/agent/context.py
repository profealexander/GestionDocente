"""
Context Engine — historial de conversación por sesión (RAM con TTL).
TODO: migrar a Redis para persistir entre reinicios (igual que StateStore en bot/state.py).
"""
from __future__ import annotations

import time
from collections import defaultdict

from .schemas import AgentContext

# session_id → list of {role, content}
_store: dict[str, list[dict]] = defaultdict(list)
# session_id → last-access timestamp (monotonic)
_last_access: dict[str, float] = {}

_MAX_HISTORY = 10   # turnos a conservar por sesión
_SESSION_TTL = 7200  # segundos sin actividad antes de evictar (2h)
_CLEANUP_EVERY = 200  # evictar entradas expiradas cada N operaciones save()
_save_counter = 0


def _cleanup_stale() -> None:
    cutoff = time.monotonic() - _SESSION_TTL
    stale = [sid for sid, t in _last_access.items() if t < cutoff]
    for sid in stale:
        _store.pop(sid, None)
        _last_access.pop(sid, None)


def load(user_id: str, session_id: str) -> AgentContext:
    _last_access[session_id] = time.monotonic()
    return AgentContext(
        user_id=user_id,
        session_id=session_id,
        history=list(_store[session_id]),
    )


def save(ctx: AgentContext, user_text: str, assistant_text: str) -> None:
    global _save_counter
    history = _store[ctx.session_id]
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_text})
    if len(history) > _MAX_HISTORY * 2:
        _store[ctx.session_id] = history[-(_MAX_HISTORY * 2):]
    _last_access[ctx.session_id] = time.monotonic()

    _save_counter += 1
    if _save_counter >= _CLEANUP_EVERY:
        _save_counter = 0
        _cleanup_stale()
