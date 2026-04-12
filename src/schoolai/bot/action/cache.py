"""Caché ligero de resultados pendientes (esperan que el usuario elija curso)."""

from __future__ import annotations

from schoolai.skills.utils.schema import ExtractionResult

_pending_cache: dict[int, ExtractionResult] = {}
_PENDING_CACHE_MAX = 500
_PENDING_CACHE_TTL = 1800  # 30 minutos


def _evict_stale_pending() -> None:
    """Remove stale entries if cache exceeds max size."""
    if len(_pending_cache) > _PENDING_CACHE_MAX:
        keys = list(_pending_cache.keys())
        for k in keys[: len(keys) // 2]:
            _pending_cache.pop(k, None)


def store_pending(user_id: int, result: ExtractionResult) -> None:
    _evict_stale_pending()
    _pending_cache[user_id] = result


def pop_pending(user_id: int) -> ExtractionResult | None:
    return _pending_cache.pop(user_id, None)
