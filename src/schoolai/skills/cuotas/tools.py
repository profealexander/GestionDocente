"""Tools registry para CuotaSkill.

Cada tool es una función Python pura (sin Telegram) que:
  - maneja su propia sesión de DB
  - retorna datos tipados
  - incluye metadata para LLM fallback (Fase 2)

Uso desde handler.py:
    from schoolai.skills.cuotas.tools import run_tool, TOOLS
    result = await run_tool("create_actividad", nombre="Paseo", monto=50.0)

Uso desde LLM fallback (Fase 2):
    groq_tools = [t.to_tool_dict() for t in TOOLS]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# ── Definición de tool ─────────────────────────────────────────────────────────


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema — OpenAI-compatible tool format
    fn: Callable  # función async Python

    def to_tool_dict(self) -> dict:
        """Convierte al formato tool definition OpenAI-compatible (Groq, Z.AI, OpenAI, etc.)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ── Funciones Python (sin Telegram, sin sesión externa) ───────────────────────


async def _create_actividad(
    nombre: str,
    monto: float,
    teacher_id: int | None = None,
    descripcion: str | None = None,
):
    from schoolai.db.connection import async_session
    from schoolai.skills.cuotas.service import create_actividad

    async with async_session() as session:
        return await create_actividad(session, nombre, monto, teacher_id, descripcion)


async def _list_actividades(teacher_id: int | None = None, only_active: bool = True):
    from schoolai.db.connection import async_session
    from schoolai.skills.cuotas.service import get_actividades

    async with async_session() as session:
        return await get_actividades(session, teacher_id=teacher_id, only_active=only_active)


async def _get_actividad_by_nombre(nombre: str):
    from schoolai.db.connection import async_session
    from schoolai.skills.cuotas.service import get_actividad_by_nombre

    async with async_session() as session:
        return await get_actividad_by_nombre(session, nombre)


async def _get_estado_actividad(actividad_id: int):
    from schoolai.db.connection import async_session
    from schoolai.skills.cuotas.service import get_estado_actividad

    async with async_session() as session:
        return await get_estado_actividad(session, actividad_id)


async def _add_participantes(actividad_id: int, student_ids: list[int]) -> int:
    from schoolai.db.connection import async_session
    from schoolai.skills.cuotas.service import add_participantes

    async with async_session() as session:
        return await add_participantes(session, actividad_id, student_ids)


async def _add_students_from_course(actividad_id: int, course_abbrev: str) -> int:
    """Agrega todos los alumnos activos de un curso a la actividad."""
    from schoolai.db.connection import async_session
    from schoolai.skills.cuotas.service import add_participantes, get_students_in_grade
    from schoolai.skills.homework.repository import find_grade

    async with async_session() as session:
        grade = await find_grade(session, course_abbrev)
        if not grade:
            return 0
        students = await get_students_in_grade(session, grade.id)
        return await add_participantes(session, actividad_id, [s.id for s in students])


async def _register_pago(
    actividad_id: int,
    student_id: int,
    monto: float,
    notas: str | None = None,
):
    from schoolai.db.connection import async_session
    from schoolai.skills.cuotas.service import register_pago

    async with async_session() as session:
        return await register_pago(session, actividad_id, student_id, monto, notas)


async def _export_actividad(actividad_id: int) -> tuple | None:
    """Retorna (actividad, participantes, xlsx_bytes) o None si no existe."""
    from schoolai.db.connection import async_session
    from schoolai.skills.cuotas.exporter import export_actividad_excel
    from schoolai.skills.cuotas.service import get_estado_actividad

    async with async_session() as session:
        actividad, participantes = await get_estado_actividad(session, actividad_id)
    if not actividad or not participantes:
        return None
    xlsx = export_actividad_excel(actividad, participantes)
    return actividad, participantes, xlsx


# ── Registry de tools ──────────────────────────────────────────────────────────

TOOLS: list[ToolDef] = [
    ToolDef(
        name="create_actividad",
        description="Creates a new school activity or fee (cuota) with a name and amount.",
        parameters={
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "Activity name, e.g.: Paseo de Grado",
                },
                "monto": {"type": "number", "description": "Total amount in dollars, e.g.: 50"},
                "course": {
                    "type": "string",
                    "description": "Course abbreviation to auto-enroll students, e.g.: 3bt. Optional.",
                },
            },
            "required": ["nombre", "monto"],
        },
        fn=_create_actividad,
    ),
    ToolDef(
        name="list_actividades",
        description="Lists all active activities for the teacher.",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
        fn=_list_actividades,
    ),
    ToolDef(
        name="get_estado_actividad",
        description="Queries the payment status of an activity by name.",
        parameters={
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "Full or partial activity name",
                },
            },
            "required": ["nombre"],
        },
        fn=_get_actividad_by_nombre,  # resuelve nombre → id internamente en skill.py
    ),
    ToolDef(
        name="register_pago",
        description="Records a payment from one or more students for an activity.",
        parameters={
            "type": "object",
            "properties": {
                "nombres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Last names or first names of the students who paid",
                },
                "monto": {"type": "number", "description": "Amount paid in dollars"},
                "actividad": {"type": "string", "description": "Activity name"},
                "course": {"type": "string", "description": "Course abbreviation. Optional."},
            },
            "required": ["nombres", "monto"],
        },
        fn=_register_pago,
    ),
    ToolDef(
        name="export_reporte",
        description="Generates and sends an Excel payment report for an activity.",
        parameters={
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Activity name to export"},
            },
            "required": [],
        },
        fn=_export_actividad,
    ),
    ToolDef(
        name="add_students_from_course",
        description="Enrolls all active students from a course as participants in an activity.",
        parameters={
            "type": "object",
            "properties": {
                "actividad_id": {"type": "integer", "description": "Activity ID"},
                "course": {"type": "string", "description": "Course abbreviation, e.g.: 3bt"},
            },
            "required": ["actividad_id", "course"],
        },
        fn=_add_students_from_course,
    ),
]

# Índice por nombre para lookup O(1)
TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


async def run_tool(name: str, **kwargs) -> Any:
    """Ejecuta una tool por nombre. Lanza KeyError si no existe."""
    tool = TOOLS_BY_NAME[name]
    return await tool.fn(**kwargs)


# ── LLM Fallback (Groq) ────────────────────────────────────────────────────────


def _tool_call_to_extract(tool_name: str, args: dict):
    """Convierte una tool call de Groq a CuotaExtract."""
    from schoolai.skills.cuotas.extractor import CuotaExtract

    if tool_name == "create_actividad":
        return CuotaExtract(
            action="create",
            nombre=args.get("nombre"),
            monto=args.get("monto"),
            course=args.get("course"),
            complete=bool(args.get("nombre") and args.get("monto")),
        )
    if tool_name == "list_actividades":
        return CuotaExtract(action="list", complete=True)
    if tool_name == "get_estado_actividad":
        return CuotaExtract(
            action="query",
            nombre=args.get("nombre"),
            complete=bool(args.get("nombre")),
        )
    if tool_name == "register_pago":
        return CuotaExtract(
            action="pago",
            nombres=args.get("nombres", []),
            monto=args.get("monto"),
            nombre=args.get("actividad"),
            course=args.get("course"),
            complete=bool(args.get("nombres") and args.get("monto")),
        )
    if tool_name == "export_reporte":
        return CuotaExtract(
            action="export",
            nombre=args.get("nombre"),
            complete=False,
        )
    return None


async def llm_fallback(text: str):
    """Llama a Groq cuando extract_cuota() devuelve None. Retorna CuotaExtract o None."""
    from schoolai.skills.llm.tool_caller import call_groq_tools

    result = await call_groq_tools(
        text,
        TOOLS,
        system_prompt=(
            "You are a school assistant. Analyze the teacher's message and call "
            "the most appropriate tool. Respond only with a tool call."
        ),
    )
    if result is None:
        return None
    tool_name, args = result
    return _tool_call_to_extract(tool_name, args)
