"""AttendanceController — record and query attendance via existing _tools/."""
from __future__ import annotations

from typing import Any

from schoolai.skills.orchestrator._tools.attendance import _query_attendance, _record_attendance
from schoolai.skills.orchestrator._tools.courses import _list_courses

from .base import BaseDomainController


class AttendanceController(BaseDomainController):
    name = "attendance"

    tools = [
        {
            "name": "record_attendance",
            "description": "Register absent, late, or justified students in a course.",
            "parameters": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Student names",
                },
                "course": {
                    "type": "string",
                    "description": "Course code or name, e.g. '3BT'",
                },
                "date": {
                    "type": "string",
                    "description": "Date: 'today', 'yesterday', or DD/MM/YYYY",
                    "default": "today",
                },
                "status": {
                    "type": "string",
                    "enum": ["absent", "late", "justified", "all_present"],
                    "default": "absent",
                },
            },
            "required": ["names", "course"],
        },
        {
            "name": "query_attendance",
            "description": "Query attendance records for a course on a given period.",
            "parameters": {
                "course": {"type": "string", "description": "Course code or name"},
                "period": {
                    "type": "string",
                    "description": "Period: 'today', 'yesterday', 'week', 'month'",
                    "default": "today",
                },
            },
            "required": ["course"],
        },
        {
            "name": "list_courses",
            "description": "List available courses, optionally filtered by level.",
            "parameters": {
                "level": {"type": "string", "description": "Optional level filter"},
            },
            "required": [],
        },
    ]

    async def execute_tool(self, tool: str, params: dict[str, Any], user_id: str) -> str:
        if tool == "record_attendance":
            return await _record_attendance(
                telegram_id=int(user_id),
                names=params.get("names", []),
                course=params.get("course", ""),
                date=params.get("date", "today"),
                status=params.get("status", "absent"),
            )
        if tool == "query_attendance":
            # _query_attendance takes a list of courses and a period string
            return await _query_attendance(
                courses=[params.get("course", "")],
                period=params.get("period", "today"),
            )
        if tool == "list_courses":
            return await _list_courses(level=params.get("level"))
        raise ValueError(f"Unknown tool: {tool}")
