"""AttendanceAgent — skill agent especializado en asistencia."""

from __future__ import annotations

from schoolai.skills.orchestrator.skill_agents.base import TELEGRAM_FORMAT, SkillAgentBase

_SYSTEM_PROMPT = (
    "You are SchoolAI's attendance assistant for Ecuadorian teachers.\n"
    "Today is {today}.\n"
    "\n"
    "INSTRUCTIONS:\n"
    "- Focus ONLY on attendance tasks: recording absences, tardiness, justified absences, "
    "and querying attendance records.\n"
    "- Ignore any parts of the teacher's message that are about homework, payments, "
    "or other topics.\n"
    "- If the teacher mentions an education level (bachillerato, egb, básica, inicial) "
    "without the exact course code, call 'listar_cursos' first, then proceed.\n"
    "- Use 'registrar_asistencia' with status:\n"
    "    absent = missed class\n"
    "    late = tardy\n"
    "    justified = excused absence\n"
    "    all_present = everyone attended (pass empty nombres list)\n"
    "- Use 'consultar_asistencia' to query records for one or more courses.\n"
    "- Always reply in Spanish, concisely.\n"
    "- Never invent student names or dates."
    + TELEGRAM_FORMAT
)


class AttendanceAgent(SkillAgentBase):
    """Agente especializado en registro y consulta de asistencia."""

    name = "attendance"
    system_prompt_template = _SYSTEM_PROMPT

    @property
    def tools(self):
        from schoolai.skills.orchestrator.tools import TOOLS_BY_NAME
        return [
            TOOLS_BY_NAME["registrar_asistencia"],
            TOOLS_BY_NAME["consultar_asistencia"],
            TOOLS_BY_NAME["listar_cursos"],
        ]

    async def _execute_tool(self, name: str, args: dict) -> str:
        from schoolai.skills.orchestrator.tools import execute_tool
        return await execute_tool(name, args)
