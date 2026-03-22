"""Tools registry para AttendanceSkill."""

from __future__ import annotations

from schoolai.skills.cuotas.tools import ToolDef  # reutiliza la misma clase

_SYSTEM_PROMPT = (
    "Eres asistente escolar. El docente registra inasistencias o consulta asistencia. "
    "Analiza el mensaje y llama la herramienta correcta. Solo responde con una tool call."
)

TOOLS: list[ToolDef] = [
    ToolDef(
        name="mark_attendance",
        description="Registra inasistencias, atrasos o justificados de estudiantes en un curso.",
        parameters={
            "type": "object",
            "properties": {
                "nombres": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Apellidos o nombres de los estudiantes. Lista vacía si todos asistieron.",
                },
                "curso":  {"type": "string",  "description": "Abreviatura del curso, ej: 3bt, 8egb, prep"},
                "fecha":  {"type": "string",  "description": "today, yesterday, o YYYY-MM-DD. Default: today"},
                "status": {
                    "type": "string",
                    "enum": ["absent", "late", "justified", "all_present"],
                    "description": "absent=falta, late=atraso, justified=justificado, all_present=todos presentes",
                },
            },
            "required": ["nombres", "curso"],
        },
        fn=None,
    ),
    ToolDef(
        name="query_attendance",
        description="Consulta el registro de asistencia de uno o varios cursos.",
        parameters={
            "type": "object",
            "properties": {
                "cursos": {"type": "array", "items": {"type": "string"}, "description": "Abreviaturas de cursos"},
                "period": {"type": "string", "description": "today, yesterday, week, month, trimester_1/2/3"},
            },
            "required": ["cursos"],
        },
        fn=None,
    ),
]

TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


def _tool_call_to_result(tool_name: str, args: dict):
    from schoolai.skills.utils.schema import (
        AttendanceExtract, ExtractionResult, QueryExtract,
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
    from schoolai.skills.llm.tool_caller import call_groq_tools

    result = await call_groq_tools(text, TOOLS, _SYSTEM_PROMPT)
    if result is None:
        return None
    tool_name, args = result
    return _tool_call_to_result(tool_name, args)
