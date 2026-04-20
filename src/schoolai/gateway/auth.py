"""
Auth + rate limiting for the Gateway.
Reuses allowed-users list from settings; rate limit is per user_id.
"""
from __future__ import annotations

from collections import defaultdict
from time import monotonic

from schoolai.config import settings

# Simple in-process token bucket: max 20 messages per 60s per user
_RATE_LIMIT = 20
_WINDOW = 60.0

_buckets: dict[str, list[float]] = defaultdict(list)


class AuthError(Exception):
    pass


class RateLimitError(Exception):
    pass


def check_auth(user_id: str) -> None:
    allowed = {str(u) for u in settings.allowed_user_ids}
    if user_id not in allowed:
        raise AuthError(f"User {user_id} not authorized")


def check_rate_limit(user_id: str) -> None:
    now = monotonic()
    timestamps = _buckets[user_id]
    # Remove timestamps outside the window
    _buckets[user_id] = [t for t in timestamps if now - t < _WINDOW]
    if len(_buckets[user_id]) >= _RATE_LIMIT:
        raise RateLimitError(f"Rate limit exceeded for user {user_id}")
    _buckets[user_id].append(now)
