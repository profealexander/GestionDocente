"""Generic per-user state store with optional Redis persistence and TTL cleanup."""
from __future__ import annotations

import dataclasses
import json
import time
from datetime import date, datetime
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")

_redis_client: Any = None
_REDIS_TTL_DEFAULT = 3600
_REDIS_TTL_LONG = 86400
_ALL_STORES: list["StateStore"] = []


def init_redis(client: Any) -> None:
    global _redis_client
    _redis_client = client


# ── JSON codec — replaces pickle to prevent RCE from tampered Redis data ───────

class _DateEncoder(json.JSONEncoder):
    """Encodes date/datetime as {"__type__": "date", "value": "YYYY-MM-DD"} so
    that the object_hook decoder in _rget can reconstruct them without eval/exec."""

    def default(self, obj: object) -> object:
        if isinstance(obj, datetime):
            return {"__type__": "datetime", "value": obj.isoformat()}
        if isinstance(obj, date):
            return {"__type__": "date", "value": obj.isoformat()}
        return super().default(obj)


def _date_hook(d: dict) -> Any:
    """object_hook for json.loads — reconstructs date/datetime from sentinel dicts."""
    t = d.get("__type__")
    if t == "date":
        return date.fromisoformat(d["value"])
    if t == "datetime":
        return datetime.fromisoformat(d["value"])
    return d


def _rset(key: str, obj: object, ttl: int) -> None:
    if _redis_client is None:
        return
    try:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            payload = dataclasses.asdict(obj)
        else:
            payload = obj
        raw = json.dumps(payload, cls=_DateEncoder).encode()
        _redis_client.setex(key, ttl, raw)
    except Exception:
        pass


def _rget(key: str) -> Any:
    if _redis_client is None:
        return None
    try:
        raw = _redis_client.get(key)
        if not raw:
            return None
        return json.loads(raw, object_hook=_date_hook)
    except Exception:
        # Covers JSONDecodeError (old pickle data after migration) and any other error.
        return None


def _rdel(key: str) -> None:
    if _redis_client is None:
        return
    try:
        _redis_client.delete(key)
    except Exception:
        pass


class StateStore(Generic[T]):
    """Per-user state store. Auto-registers for global cleanup.

    Args:
        key:        Redis key prefix (e.g. "db", "jornada").
        use_redis:  Persist to Redis so state survives bot restarts.
        ttl:        TTL in seconds (both RAM eviction and Redis expiry).
        decode:     Optional callable ``(dict) -> T`` to reconstruct the stored
                    object from its JSON-decoded dict form.  Required when the
                    store uses Redis and the value is a dataclass — without it
                    Redis cache misses will return ``None`` (fresh state).
    """

    def __init__(
        self,
        key: str,
        *,
        use_redis: bool = False,
        ttl: int = _REDIS_TTL_DEFAULT,
        decode: Callable[[Any], T] | None = None,
    ):
        self._key = key
        self._ttl = ttl
        self._use_redis = use_redis
        self._decode = decode
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
            raw = _rget(f"{self._key}:{user_id}")
            if raw is not None and self._decode is not None:
                try:
                    obj = self._decode(raw)
                    self._data[user_id] = obj
                    self._timestamps[user_id] = time.monotonic()
                except Exception:
                    pass  # corrupt or schema-changed data — start fresh
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
                        raw = _rget(key_str)
                        if raw is not None and self._decode is not None:
                            try:
                                results[uid] = self._decode(raw)
                            except Exception:
                                pass
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

    def cleanup_where(self, predicate: Callable[[T], bool]) -> int:
        """Elimina entradas en memoria donde predicate(value) es True.

        Útil para limpiar entradas de acuerdo a criterios de dominio
        (ej: sesiones de jornada de otro día).
        """
        stale = [uid for uid, val in self._data.items() if predicate(val)]
        for uid in stale:
            self._data.pop(uid, None)
            self._timestamps.pop(uid, None)
        return len(stale)


def clear_all_user_state(user_id: int) -> None:
    """Clear ALL state for a user. Used by /cancelar command."""
    for store in _ALL_STORES:
        store.clear(user_id)


def cleanup_all_stale() -> int:
    """Cleanup stale entries across all registered stores."""
    return sum(store.cleanup_stale() for store in _ALL_STORES)
