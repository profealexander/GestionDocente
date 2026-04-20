from __future__ import annotations

from typing import Any

from schoolai.skills.orchestrator._tools.courses import _list_courses

from .base import BaseDomainController


class GeneralController(BaseDomainController):
    name = "general"

    tools = [
        {
            "name": "list_courses",
            "description": "List available courses.",
            "parameters": {
                "level": {"type": "string", "description": "Optional level filter"},
            },
            "required": [],
        },
    ]

    async def execute_tool(self, tool: str, params: dict[str, Any], user_id: str) -> str:
        if tool == "list_courses":
            return await _list_courses(level=params.get("level"))
        raise ValueError(f"Unknown tool: {tool}")
