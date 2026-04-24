"""Registry for text message interceptors — replaces the manual if-chain in handlers.py."""
from __future__ import annotations

from typing import Callable

from loguru import logger


class TextInterceptorRegistry:
    def __init__(self) -> None:
        self._interceptors: list[tuple[int, str, Callable]] = []

    def register(self, priority: int = 50, name: str = "") -> Callable:
        """Decorator: @text_interceptors.register(priority=10)"""
        def decorator(fn: Callable) -> Callable:
            n = name or fn.__name__
            self._interceptors.append((priority, n, fn))
            self._interceptors.sort(key=lambda x: x[0])
            return fn
        return decorator

    async def run(self, update, user_id: int) -> bool:
        """Run interceptors in priority order. Returns True if any handled the message."""
        for _, name, fn in self._interceptors:
            try:
                if await fn(update, user_id):
                    logger.debug(f"[interceptors] handled by {name}")
                    return True
            except Exception as e:
                logger.error(f"[interceptors] error in {name}: {e}", exc_info=True)
        return False


text_interceptors = TextInterceptorRegistry()
