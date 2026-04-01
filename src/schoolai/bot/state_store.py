"""Generic per-user state store with optional Redis persistence and TTL cleanup."""
from __future__ import annotations

import pickle
import time
from typing import Any, Generic, TypeVar

T = TypeVar("T")

_redis_client: Any = None
_REDIS_TTL_DEFAULT = 3600
_REDIS_TTL_LONG = 86400
_ALL_STORES: list["StateStore"] = []


def init_redis(client: Any) -> None:
    global _redis_client
    _redis_client = client


def _rset(key: str, obj: object, ttl: int) -> None:
    if _redis_client is None:
        return
    try:
        _redis_client.setex(key, ttl, pickle.dumps(obj))
    except Exception:
        pass


def _rget(key: str) -> Any:
    if _redis_client is None:
        return None
    try:
        raw = _redis_client.get(key)
        return pickle.loads(raw) if raw else None  # nosec B301
    except Exception:
        return None


def _rdel(key: str) -> None:
    if _redis_client is None:
        return
    try:
        _redis_client.delete(key)
    except Exception:
        pass


class StateStore(Generic[T]):
    """Per-user state store. Auto-registers for global cleanup."""

    def __init__(self, key: str, *, use_redis: bool = False, ttl: int = _REDIS_TTL_DEFAULT):
        self._key = key
        self._ttl = ttl
        self._use_redis = use_redis
        self._data: dict[int, T] = {}
        self._timestamps: dict[int, float] = {}
        _ALL_STORES.append(self)

    def set(self, user_id: int, state: T) -> None:
        self._data[user_id] = state
        self._timestamps[user_id] = time.monotonic()
        if self._use_redis:
            _rset(f"{self._key}:{user_id}", state, self._ttl)

    def get(self, user_id: int) -> T | None:
        if user_id not in self._data and self._use_redis:
            obj = _rget(f"{self._key}:{user_id}")
            if obj is not None:
                self._data[user_id] = obj
                self._timestamps[user_id] = time.monotonic()
        return self._data.get(user_id)

    def clear(self, user_id: int) -> None:
        self._data.pop(user_id, None)
        self._timestamps.pop(user_id, None)
        if self._use_redis:
            _rdel(f"{self._key}:{user_id}")

    def pop(self, user_id: int) -> T | None:
        val = self.get(user_id)
        self.clear(user_id)
        return val

    def scan_all(self) -> list[tuple[int, T]]:
        """Returns all entries — in-memory dict + Redis scan for entries not yet loaded."""
        results: dict[int, T] = dict(self._data)
        if self._use_redis and _redis_client is not None:
            try:
                for key in _redis_client.scan_iter(f"{self._key}:*"):
                    key_str = key.decode() if isinstance(key, bytes) else key
                    try:
                        uid = int(key_str.rsplit(":", 1)[1])
                    except (ValueError, IndexError):
                        continue
                    if uid not in results:
                        obj = _rget(key_str)
                        if obj is not None:
                            results[uid] = obj
            except Exception:
                pass
        return list(results.items())

    def cleanup_stale(self) -> int:
        now = time.monotonic()
        expired = [uid for uid, ts in self._timestamps.items() if now - ts > self._ttl]
        for uid in expired:
            self._data.pop(uid, None)
            self._timestamps.pop(uid, None)
        return len(expired)


def clear_all_user_state(user_id: int) -> None:
    """Clear ALL state for a user. Used by /cancelar command."""
    for store in _ALL_STORES:
        store.clear(user_id)


def cleanup_all_stale() -> int:
    """Cleanup stale entries across all registered stores."""
    return sum(store.cleanup_stale() for store in _ALL_STORES)
