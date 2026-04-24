from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TaskSpec(BaseModel):
    channel: Literal["telegram", "web", "cli", "cron"]
    domain: Literal["attendance", "homework", "cuotas", "reports", "web_search", "general"]
    intent: Literal["query", "record", "delete", "search", "chat"]
    entities: list[str]
    raw_text: str
    user_id: str
    session_id: str


class MessageSpec(BaseModel):
    channel: Literal["telegram", "web", "cli", "cron"]
    user_id: str
    session_id: str
    text: str
    # Optional metadata from the channel adapter
    extra: dict = {}


class ResponseSpec(BaseModel):
    session_id: str
    text: str
    domain: str
    intent: str


# Alias usado por app.py — mismo shape, nombre explícito para el OpenAPI spec
AgentResponseOut = ResponseSpec
