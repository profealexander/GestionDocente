"""Tools registry para HomeworkSkill y HWReportSkill."""

from __future__ import annotations

from schoolai.skills.cuotas.tools import ToolDef

_SYSTEM_PROMPT = (
    "You are a school assistant. The teacher is registering homework or reporting students who did not submit. "
    "Analyze the message and call the correct tool. Respond only with a tool call."
)

TOOLS: list[ToolDef] = [
    ToolDef(
        name="create_homework",
        description="Records a new homework assignment, activity, or evaluation for a course.",
        parameters={
            "type": "object",
            "properties": {
                "descripcion": {
                    "type": "string",
                    "description": "Full description of the homework or assignment",
                },
                "curso": {"type": "string", "description": "Course abbreviation, e.g.: 3bt"},
                "materias": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of subjects. Include all if the assignment spans multiple subjects. "
                        "E.g.: ['Philosophy', 'Accounting']"
                    ),
                },
                "fecha_entrega": {
                    "type": "string",
                    "description": "Due date YYYY-MM-DD or day name. Optional.",
                },
            },
            "required": ["descripcion", "curso"],
        },
        fn=None,
    ),
    ToolDef(
        name="report_missing",
        description="Reports students who did not submit or did not complete an assignment.",
        parameters={
            "type": "object",
            "properties": {
                "nombres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Last names of students who did not comply",
                },
                "curso": {"type": "string", "description": "Course abbreviation"},
                "tarea_ref": {"type": "integer", "description": "Homework number, e.g.: 3"},
                "materia": {"type": "string", "description": "Subject name. Optional."},
                "status": {
                    "type": "string",
                    "enum": ["missing", "late", "partial"],
                    "description": "missing=not submitted, late=submitted late, partial=incomplete",
                },
            },
            "required": ["nombres", "curso"],
        },
        fn=None,
    ),
]

TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


def _tool_call_to_result(tool_name: str, args: dict):
    from schoolai.skills.utils.schema import (
        ExtractionResult,
        HomeworkExtract,
        HomeworkReportExtract,
    )

    if tool_name == "create_homework":
        materias = args.get("materias", [])
        if isinstance(materias, str):
            materias = [materias] if materias else []
        # compat con campo singular legado
        if not materias and args.get("materia"):
            materias = [args["materia"]]
        return ExtractionResult(
            intent="homework",
            data=HomeworkExtract(
                description=args.get("descripcion", ""),
                course=args.get("curso"),
                subject=materias[0] if materias else None,
                subjects=materias,
                delivery_date=args.get("fecha_entrega"),
                complete=bool(args.get("curso") and args.get("descripcion")),
            ),
        )
    if tool_name == "report_missing":
        return ExtractionResult(
            intent="homework_report",
            data=HomeworkReportExtract(
                names=args.get("nombres", []),
                homework_ref=args.get("tarea_ref"),
                course=args.get("curso"),
                subject=args.get("materia"),
                status=args.get("status", "missing"),
                complete=bool(args.get("curso")),
            ),
        )
    return None


async def llm_fallback(text: str):
    """Fallback Groq para HomeworkSkill / HWReportSkill. Retorna ExtractionResult o None."""
    from schoolai.skills.llm.tool_caller import call_groq_tools

    result = await call_groq_tools(text, TOOLS, _SYSTEM_PROMPT)
    if result is None:
        return None
    tool_name, args = result
    return _tool_call_to_result(tool_name, args)
