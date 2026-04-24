"""ReplAgent — agente especializado en consultas analíticas via Python REPL.

Usa GPT-OSS 20B (Groq) para análisis/SQL/código.
Validado: genera `await query(sql)` correcto en benchmark 3/3 prompts.
"""

from __future__ import annotations

from schoolai.skills.orchestrator.skill_agents.base import TELEGRAM_FORMAT, SkillAgentBase

_SYSTEM_PROMPT = (
    "You are SchoolAI's data analyst assistant for Ecuadorian teachers.\n"
    "Today is {today}.\n"
    "\n"
    "INSTRUCTIONS:\n"
    "- Answer statistical, aggregate, or analytical questions using 'python_repl'.\n"
    "- Use 'list_courses' first if you need course abbreviations.\n"
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
    "- Always reply in Spanish, concisely.\n" + TELEGRAM_FORMAT
)


class ReplAgent(SkillAgentBase):
    """Agente analítico — usa GPT-OSS 20B (Groq) para código Python/SQL."""

    name = "repl"
    system_prompt_template = _SYSTEM_PROMPT
    llm_override = "groq/openai/gpt-oss-20b"

    @property
    def tools(self):
        from schoolai.skills.orchestrator.tools import TOOLS_BY_NAME

        return [
            TOOLS_BY_NAME["python_repl"],
            TOOLS_BY_NAME["list_courses"],
        ]

    async def _execute_tool(self, name: str, args: dict) -> str:
        from schoolai.skills.orchestrator.tools import execute_tool

        return await execute_tool(name, args)
