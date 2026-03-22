"""Tools registry para QuerySkill."""

from __future__ import annotations

from schoolai.skills.cuotas.tools import ToolDef

_SYSTEM_PROMPT = (
    "Eres asistente escolar. El docente quiere consultar asistencia o tareas. "
    "Analiza el mensaje y llama la herramienta correcta. Solo responde con una tool call."
)

TOOLS: list[ToolDef] = [
    ToolDef(
        name="query_attendance",
        description="Consulta el registro de asistencia de uno o varios cursos en un período.",
        parameters={
            "type": "object",
            "properties": {
                "cursos": {"type": "array", "items": {"type": "string"}, "description": "Abreviaturas de cursos, ej: ['3bt', '8egb']"},
                "period": {"type": "string", "description": "today, yesterday, week, month, trimester_1/2/3"},
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
                "cursos":  {"type": "array", "items": {"type": "string"}, "description": "Abreviaturas de cursos"},
                "period":  {"type": "string", "description": "today, yesterday, week, month"},
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

    result = await call_groq_tools(text, TOOLS, _SYSTEM_PROMPT)
    if result is None:
        return None
    tool_name, args = result
    return _tool_call_to_result(tool_name, args)
