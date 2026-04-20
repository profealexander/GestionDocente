"""
ReportsController — genera PDFs de asistencia y tareas.
El Executor retorna los bytes del PDF; el canal (Telegram) los envía como documento.
"""
from __future__ import annotations

from typing import Any

from schoolai.skills.orchestrator._tools.reports import _report_attendance_pdf, _report_homework_pdf

from .base import BaseDomainController


class ReportsController(BaseDomainController):
    name = "reports"

    tools = [
        {
            "name": "attendance_pdf",
            "description": "Generate a PDF attendance report for a course.",
            "parameters": {
                "course": {"type": "string", "description": "Course code or name"},
                "date_from": {"type": "string", "description": "Start date (today / DD/MM/YYYY)", "default": "today"},
                "date_to": {"type": "string", "description": "End date (DD/MM/YYYY). If omitted, same as date_from."},
            },
            "required": ["course"],
        },
        {
            "name": "homework_pdf",
            "description": "Generate a PDF report with pending homework assignments for a course.",
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
            # Store bytes in a temp file; return the path for the channel to send
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="att_") as f:
                f.write(pdf_bytes)
                return f"PDF:{f.name}"

        if tool == "homework_pdf":
            pdf_bytes = await _report_homework_pdf(
                telegram_id=int(user_id),
                course=params.get("course", ""),
            )
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="hw_") as f:
                f.write(pdf_bytes)
                return f"PDF:{f.name}"

        raise ValueError(f"Unknown tool: {tool}")
