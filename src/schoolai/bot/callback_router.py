"""Central callback query router — replaces 29 individual CallbackQueryHandler registrations."""
from __future__ import annotations

from typing import Callable

from loguru import logger


class CallbackRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable] = {}
        self._sorted: list[tuple[str, Callable]] = []

    def register(self, prefix: str) -> Callable:
        """Decorator: @callback_router.register("my_prefix:") or ("my_prefix_")"""
        def decorator(fn: Callable) -> Callable:
            self._handlers[prefix] = fn
            self._sorted = sorted(
                self._handlers.items(), key=lambda x: len(x[0]), reverse=True,
            )
            return fn
        return decorator

    async def route(self, update, context) -> None:
        """Single entry point — registered once in main.py as CallbackQueryHandler."""
        data = update.callback_query.data
        for prefix, handler in self._sorted:
            if data.startswith(prefix):
                await handler(update, context)
                return
        await update.callback_query.answer()
        logger.warning(
            f"[callback_router] unhandled data={data!r} user={update.effective_user.id}",
        )


callback_router = CallbackRouter()
