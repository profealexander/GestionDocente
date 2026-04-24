"""
ReportsController — genera PDFs de asistencia y tareas.
El Executor retorna la ruta al PDF temporal; el canal lo envía como documento.
"""
from __future__ import annotations

import tempfile
from typing import Any

from schoolai.skills.orchestrator._tools.reports import (
    _report_attendance_pdf,
    _report_homework_pdf,
)

from .base import BaseDomainController


def _write_temp_pdf(pdf_bytes: bytes, prefix: str) -> str:
    """Write PDF bytes to a temp file and return 'PDF:<path>'."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix=prefix) as tmp:
        tmp.write(pdf_bytes)
        return f"PDF:{tmp.name}"


class ReportsController(BaseDomainController):
    name = "reports"

    tools = [
        {
            "name": "attendance_pdf",
            "description": "Generate a PDF attendance report for a course.",
            "parameters": {
                "course": {"type": "string", "description": "Course code or name"},
                "date_from": {
                    "type": "string",
                    "description": "Start date (today / DD/MM/YYYY)",
                    "default": "today",
                },
                "date_to": {
                    "type": "string",
                    "description": "End date (DD/MM/YYYY). If omitted, same as date_from.",
                },
            },
            "required": ["course"],
        },
        {
            "name": "homework_pdf",
            "description": "Generate a PDF report with pending homework assignments.",
            "parameters": {
                "course": {"type": "string", "description": "Course code or name"},
            },
            "required": ["course"],
        },
    ]

    async def execute_tool(self, tool: str, params: dict[str, Any], user_id: str) -> str:
        if tool == "attendance_pdf":
            pdf_bytes = await _report_attendance_pdf(
                telegram_id=int(user_id),
                course=params.get("course", ""),
                date_from=params.get("date_from", "today"),
                date_to=params.get("date_to"),
            )
            return _write_temp_pdf(pdf_bytes, "att_")

        if tool == "homework_pdf":
            pdf_bytes = await _report_homework_pdf(
                telegram_id=int(user_id),
                course=params.get("course", ""),
            )
            return _write_temp_pdf(pdf_bytes, "hw_")

        raise ValueError(f"Unknown tool: {tool}")
