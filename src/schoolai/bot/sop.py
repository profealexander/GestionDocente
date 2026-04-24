"""SOPEngine — tabla de transiciones para máquinas de estado finitas.

Inspirado en el patrón SOP (Standard Operating Procedure) de ZeroClaw.
Mapea (status, trigger) → handler_fn, con soporte para wildcards ("*").
"""

from __future__ import annotations

from collections.abc import Callable


class SOPEngine:
    """Dispatch table: (status, trigger) → async handler.

    - Use "*" as status to match regardless of current state.
    - Returns None from get_handler() when no transition is valid,
      allowing callers to reject the action with a user-visible alert.
    """

    def __init__(self, transitions: dict[tuple[str, str], Callable]) -> None:
        self._transitions = transitions

    def get_handler(self, status: str, trigger: str) -> Callable | None:
        """Returns the handler for (status, trigger) or None if not allowed."""
        return self._transitions.get((status, trigger)) or self._transitions.get(("*", trigger))

    def allowed(self, status: str, trigger: str) -> bool:
        return self.get_handler(status, trigger) is not None
