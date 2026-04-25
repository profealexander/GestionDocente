"""
Auth + rate limiting for the Gateway.
Reuses allowed-users list from settings; rate limit is per user_id.
"""
from __future__ import annotations

from time import monotonic

from schoolai.config import settings

# Simple in-process token bucket: max 20 messages per 60s per user
_RATE_LIMIT = 20
_WINDOW = 60.0

_buckets: dict[str, list[float]] = {}
_call_counter = 0
_CLEANUP_EVERY = 500  # purge stale keys every N calls


class AuthError(Exception):
    pass


class RateLimitError(Exception):
    pass


def check_auth(user_id: str) -> None:
    if settings.admin_telegram_id and str(user_id) == str(settings.admin_telegram_id):
        return
    allowed = {str(u) for u in settings.allowed_user_ids}
    if allowed and user_id not in allowed:
        raise AuthError(f"User {user_id} not authorized")


def check_rate_limit(user_id: str) -> None:
    global _call_counter
    now = monotonic()

    recent = [t for t in _buckets.get(user_id, []) if now - t < _WINDOW]
    if len(recent) >= _RATE_LIMIT:
        _buckets[user_id] = recent
        raise RateLimitError(f"Rate limit exceeded for user {user_id}")
    recent.append(now)
    _buckets[user_id] = recent

    _call_counter += 1
    if _call_counter >= _CLEANUP_EVERY:
        _call_counter = 0
        cutoff = now - _WINDOW
        stale = [uid for uid, ts in _buckets.items() if not ts or ts[-1] < cutoff]
        for uid in stale:
            del _buckets[uid]
