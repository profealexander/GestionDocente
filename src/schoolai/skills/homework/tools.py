"""Tools registry para HomeworkSkill y HWReportSkill."""

from __future__ import annotations

from schoolai.skills.cuotas.tools import ToolDef

_SYSTEM_PROMPT = (
    "Eres asistente escolar. El docente registra tareas o reporta estudiantes que no entregaron. "
    "Analiza el mensaje y llama la herramienta correcta. Solo responde con una tool call."
)

TOOLS: list[ToolDef] = [
    ToolDef(
        name="create_homework",
        description="Registra una nueva tarea, deber, actividad o evaluación para un curso.",
        parameters={
            "type": "object",
            "properties": {
                "descripcion": {"type": "string",  "description": "Descripción completa de la tarea"},
                "curso":       {"type": "string",  "description": "Abreviatura del curso, ej: 3bt"},
                "materia":     {"type": "string",  "description": "Materia o asignatura, ej: Matemáticas"},
                "fecha_entrega": {"type": "string","description": "Fecha de entrega YYYY-MM-DD o nombre día. Opcional."},
            },
            "required": ["descripcion", "curso"],
        },
        fn=None,
    ),
    ToolDef(
        name="report_missing",
        description="Reporta estudiantes que no entregaron o no cumplieron con una tarea.",
        parameters={
            "type": "object",
            "properties": {
                "nombres":    {"type": "array", "items": {"type": "string"}, "description": "Apellidos de los que no cumplieron"},
                "curso":      {"type": "string",  "description": "Abreviatura del curso"},
                "tarea_ref":  {"type": "integer", "description": "Número de tarea, ej: 3"},
                "materia":    {"type": "string",  "description": "Materia. Opcional."},
                "status":     {"type": "string",  "enum": ["missing", "late", "partial"], "description": "Tipo de incumplimiento"},
            },
            "required": ["nombres", "curso"],
        },
        fn=None,
    ),
]

TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


def _tool_call_to_result(tool_name: str, args: dict):
    from schoolai.skills.utils.schema import (
        ExtractionResult, HomeworkExtract, HomeworkReportExtract,
    )

    if tool_name == "create_homework":
        return ExtractionResult(
            intent="homework",
            data=HomeworkExtract(
                description=args.get("descripcion", ""),
                course=args.get("curso"),
                subject=args.get("materia"),
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
