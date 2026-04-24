"""HomeworkController — create, query and delete homework assignments."""
from __future__ import annotations

from typing import Any

from schoolai.skills.orchestrator._tools.homework import (
    _create_assignment,
    _delete_assignment,
    _query_assignments,
)

from .base import BaseDomainController


class HomeworkController(BaseDomainController):
    name = "homework"

    tools = [
        {
            "name": "create_assignment",
            "description": "Create a homework assignment for a course.",
            "parameters": {
                "course": {"type": "string", "description": "Course code or name"},
                "subject": {"type": "string", "description": "Subject name"},
                "description": {"type": "string", "description": "Assignment description"},
                "due_date": {
                    "type": "string",
                    "description": "Due date: 'tomorrow', day name, or DD/MM/YYYY",
                },
            },
            "required": ["course", "description"],
        },
        {
            "name": "query_assignments",
            "description": "List pending homework assignments for a course.",
            "parameters": {
                "course": {"type": "string", "description": "Course code or name"},
                "period": {
                    "type": "string",
                    "description": "Period: 'trimestre', 'week', 'month'",
                    "default": "trimestre",
                },
            },
            "required": ["course"],
        },
        {
            "name": "delete_assignment",
            "description": "Delete a homework assignment by number.",
            "parameters": {
                "number": {"type": "integer", "description": "Assignment number from the list"},
                "course": {"type": "string", "description": "Course code or name"},
            },
            "required": ["number", "course"],
        },
    ]

    async def execute_tool(self, tool: str, params: dict[str, Any], user_id: str) -> str:
        if tool == "create_assignment":
            subject = params.get("subject", "")
            return await _create_assignment(
                telegram_id=int(user_id),
                description=params.get("description", ""),
                course=params.get("course", ""),
                subjects=[subject] if subject else None,
                due_date=params.get("due_date") or None,
            )
        if tool == "query_assignments":
            # _query_assignments takes courses as a list
            return await _query_assignments(
                telegram_id=int(user_id),
                courses=[params.get("course", "")],
                period=params.get("period", "trimestre"),
            )
        if tool == "delete_assignment":
            return await _delete_assignment(
                number=params.get("number", 0),
                course=params.get("course", ""),
            )
        raise ValueError(f"Unknown tool: {tool}")
