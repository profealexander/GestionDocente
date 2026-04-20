from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PlanStep(BaseModel):
    tool: str
    params: dict[str, Any] = {}


class ActionResult(BaseModel):
    tool: str
    params: dict[str, Any]
    output: str
    success: bool = True


class AgentContext(BaseModel):
    user_id: str
    session_id: str
    history: list[dict] = []  # [{role, content}, ...]


class AgentResponse(BaseModel):
    text: str
    domain: str
    intent: str
    steps: list[ActionResult] = []
