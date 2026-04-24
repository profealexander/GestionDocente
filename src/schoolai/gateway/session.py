"""
Session manager for the Gateway.
Generates a deterministic session_id per user per day (no Redis yet — RAM only).
"""
from __future__ import annotations

import hashlib
from datetime import date


def get_session_id(user_id: str, channel: str) -> str:
    today = date.today().isoformat()
    key = f"{channel}:{user_id}:{today}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
