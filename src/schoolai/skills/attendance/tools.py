"""Tools registry para AttendanceSkill."""

from __future__ import annotations

from schoolai.skills.cuotas.tools import ToolDef  # reutiliza la misma clase

_SYSTEM_PROMPT = (
    "You are a school assistant. The teacher is recording absences or querying attendance. "
    "Analyze the message and call the correct tool. Respond only with a tool call."
)

TOOLS: list[ToolDef] = [
    ToolDef(
        name="mark_attendance",
        description="Records absences, tardiness, or justified absences for students in a course.",
        parameters={
            "type": "object",
            "properties": {
                "nombres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Last names or first names of the students. "
                        "Empty list if all students attended."
                    ),
                },
                "curso": {
                    "type": "string",
                    "description": "Course abbreviation, e.g.: 3bt, 8egb, prep",
                },
                "fecha": {
                    "type": "string",
                    "description": "today, yesterday, or YYYY-MM-DD. Default: today",
                },
                "status": {
                    "type": "string",
                    "enum": ["absent", "late", "justified", "all_present"],
                    "description": (
                        "absent=missed class, late=tardy, "
                        "justified=excused absence, all_present=everyone attended"
                    ),
                },
            },
            "required": ["nombres", "curso"],
        },
        fn=None,
    ),
    ToolDef(
        name="query_attendance",
        description="Queries the attendance record for one or more courses.",
        parameters={
            "type": "object",
            "properties": {
                "cursos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Course abbreviations, e.g.: ['3bt', '8egb']",
                },
                "period": {
                    "type": "string",
                    "description": "today, yesterday, week, month, trimester_1/2/3",
                },
            },
            "required": ["cursos"],
        },
        fn=None,
    ),
]

TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


def _tool_call_to_result(tool_name: str, args: dict):
    from schoolai.skills.utils.schema import (
        AttendanceExtract,
        ExtractionResult,
        QueryExtract,
    )

    if tool_name == "mark_attendance":
        return ExtractionResult(
            intent="attendance",
            data=AttendanceExtract(
                names=args.get("nombres", []),
                course=args.get("curso"),
                date=args.get("fecha", "today"),
                status=args.get("status", "absent"),
                complete=bool(args.get("curso")),
            ),
        )
    if tool_name == "query_attendance":
        return ExtractionResult(
            intent="query",
            data=QueryExtract(
                query_type="attendance",
                courses=args.get("cursos", []),
                period=args.get("period", "today"),
                complete=bool(args.get("cursos")),
            ),
        )
    return None


async def llm_fallback(text: str):
    """Fallback Groq para AttendanceSkill. Retorna ExtractionResult o None."""
    from schoolai.skills.llm.tool_caller import call_extractor_tools

    result = await call_extractor_tools(text, TOOLS, _SYSTEM_PROMPT)
    if result is None:
        return None
    tool_name, args = result
    return _tool_call_to_result(tool_name, args)
