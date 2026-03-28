"""ReplAgent — agente especializado en consultas analíticas via Python REPL.

Usa GLM-4.7-Flash como modelo primario porque genera código Python correcto
(await query(...) sin default_api). Gemini Flash-Lite tiene un artefacto de
entrenamiento que produce default_api.query() en su lugar.
"""

from __future__ import annotations

from schoolai.skills.orchestrator.skill_agents.base import TELEGRAM_FORMAT, SkillAgentBase

_SYSTEM_PROMPT = (
    "You are SchoolAI's data analyst assistant for Ecuadorian teachers.\n"
    "Today is {today}.\n"
    "\n"
    "INSTRUCTIONS:\n"
    "- Answer statistical, aggregate, or analytical questions using 'python_repl'.\n"
    "- Use 'listar_cursos' first if you need course abbreviations.\n"
    "- Write correct Python code using 'await query(sql)' to query the PostgreSQL database.\n"
    "- Always call 'print()' with the result so it appears in the output.\n"
    "- DO NOT use 'default_api', 'os', 'sys', 'open', or any identifier other than "
    "'query', 'today', 'now', and 'print'.\n"
    "- DB schema:\n"
    "    people(id, first_name, last_name, second_last_name)\n"
    "    students(id, person_id, grade_id, section, status)  -- status='active'|'inactive'\n"
    "    grades(id, name, level, sort_order)\n"
    "    subjects(id, name, area)\n"
    "    attendance(id, student_id, date DATE, status)  -- status='F' 'AT' 'J'\n"
    "    homework(id, grade_id, subject_id, trimester_num, sequence_num, homework TEXT, is_open BOOL)\n"
    "    actividades(id, nombre, monto, is_active)\n"
    "    actividad_participantes(id, actividad_id, student_id, total_pagado, is_complete)\n"
    "- SQL rules: use >= and < for date ranges (NOT LIKE). Strings in single quotes.\n"
    "- Always reply in Spanish, concisely.\n"
    + TELEGRAM_FORMAT
)


class ReplAgent(SkillAgentBase):
    """Agente analítico — usa GLM para generación de código Python/SQL."""

    name = "repl"
    system_prompt_template = _SYSTEM_PROMPT
    llm_override = "zai/glm-4.7-flash"  # GLM genera código Python correcto

    @property
    def tools(self):
        from schoolai.skills.orchestrator.tools import TOOLS_BY_NAME
        return [
            TOOLS_BY_NAME["python_repl"],
            TOOLS_BY_NAME["listar_cursos"],
        ]

    async def _execute_tool(self, name: str, args: dict) -> str:
        from schoolai.skills.orchestrator.tools import execute_tool
        return await execute_tool(name, args)
