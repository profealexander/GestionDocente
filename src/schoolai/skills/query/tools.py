"""Tools registry para QuerySkill."""

from __future__ import annotations

from schoolai.skills.cuotas.tools import ToolDef


def _system_prompt() -> str:
    from datetime import date
    today = date.today()
    return (
        f"You are a school assistant. Today is {today.isoformat()} ({today.strftime('%A')}).\n"
        "The teacher wants to query attendance or homework records. "
        "Analyze the message and call the correct tool. Respond only with a tool call.\n"
        "Date resolution rules:\n"
        "- 'del 17' or 'el 17' → day 17 of current month as ISO YYYY-MM-DD "
        "(use previous month if that day hasn't arrived yet this month).\n"
        "- Day names (lunes/martes/miércoles/jueves/viernes) → most recent past occurrence "
        "of that weekday (return as lowercase Spanish day name, e.g. 'jueves').\n"
        "Always respond in Spanish if a text reply is needed."
    )

TOOLS: list[ToolDef] = [
    ToolDef(
        name="query_attendance",
        description="Consulta el registro de asistencia de uno o varios cursos en un período.",
        parameters={
            "type": "object",
            "properties": {
                "cursos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Abreviaturas de cursos, ej: ['3bt', '8egb']",
                },
                "period": {
                    "type": "string",
                    "description": (
                        "today, yesterday, week, last_week, month, trimester_1/2/3, "
                        "o nombre del día en español: lunes, martes, miercoles, jueves, viernes "
                        "(resuelve al día más reciente pasado de esa semana)"
                    ),
                },
            },
            "required": ["cursos"],
        },
        fn=None,
    ),
    ToolDef(
        name="query_homework",
        description="Consulta las tareas registradas de uno o varios cursos.",
        parameters={
            "type": "object",
            "properties": {
                "cursos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Abreviaturas de cursos",
                },
                "period": {
                    "type": "string",
                    "description": (
                        "today, yesterday, week, last_week, month, "
                        "o nombre del día: lunes, martes, miercoles, jueves, viernes"
                    ),
                },
                "materia": {"type": "string", "description": "Filtrar por materia. Opcional."},
            },
            "required": ["cursos"],
        },
        fn=None,
    ),
]

TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


def _tool_call_to_result(tool_name: str, args: dict):
    from schoolai.skills.utils.schema import ExtractionResult, QueryExtract

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
    if tool_name == "query_homework":
        return ExtractionResult(
            intent="query",
            data=QueryExtract(
                query_type="homework",
                courses=args.get("cursos", []),
                period=args.get("period", "today"),
                subject=args.get("materia"),
                complete=bool(args.get("cursos")),
            ),
        )
    return None


async def llm_fallback(text: str):
    """Fallback Groq para QuerySkill. Retorna ExtractionResult o None."""
    from schoolai.skills.llm.tool_caller import call_groq_tools

    result = await call_groq_tools(text, TOOLS, _system_prompt())
    if result is None:
        return None
    tool_name, args = result
    return _tool_call_to_result(tool_name, args)
