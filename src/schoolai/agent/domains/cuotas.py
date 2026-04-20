from __future__ import annotations

from typing import Any

from schoolai.skills.orchestrator._tools.cuotas import (
    _activity_status,
    _list_activities,
    _register_payment,
)

from .base import BaseDomainController


class CuotasController(BaseDomainController):
    name = "cuotas"

    tools = [
        {
            "name": "list_activities",
            "description": "List all activities with payment tracking.",
            "parameters": {},
            "required": [],
        },
        {
            "name": "activity_status",
            "description": "Show payment status for a specific activity.",
            "parameters": {
                "name": {"type": "string", "description": "Activity name"},
            },
            "required": ["name"],
        },
        {
            "name": "register_payment",
            "description": "Register a payment for a student in an activity.",
            "parameters": {
                "activity": {"type": "string", "description": "Activity name"},
                "student": {"type": "string", "description": "Student name"},
                "amount": {"type": "number", "description": "Payment amount"},
            },
            "required": ["activity", "student", "amount"],
        },
    ]

    async def execute_tool(self, tool: str, params: dict[str, Any], user_id: str) -> str:
        if tool == "list_activities":
            return await _list_activities(telegram_id=int(user_id))
        if tool == "activity_status":
            return await _activity_status(name=params.get("name", ""))
        if tool == "register_payment":
            return await _register_payment(
                telegram_id=int(user_id),
                activity=params.get("activity", ""),
                student=params.get("student", ""),
                amount=float(params.get("amount", 0)),
            )
        raise ValueError(f"Unknown tool: {tool}")
