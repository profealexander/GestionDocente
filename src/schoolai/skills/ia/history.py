"""In-memory conversation history per user for the IA skill."""

from collections import deque

# Max messages to keep per user (system + N turns)
MAX_TURNS = 10  # 10 user+assistant pairs = 20 messages

# user_id -> deque of message dicts
_history: dict[int, deque] = {}


def get(user_id: int) -> list[dict]:
    return list(_history.get(user_id, []))


def append(user_id: int, role: str, content: str) -> None:
    if user_id not in _history:
        _history[user_id] = deque(maxlen=MAX_TURNS * 2)
    _history[user_id].append({"role": role, "content": content})


def clear(user_id: int) -> None:
    _history.pop(user_id, None)
