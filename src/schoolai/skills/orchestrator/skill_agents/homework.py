"""HomeworkAgent — skill agent especializado en tareas y deberes."""

from __future__ import annotations

from schoolai.skills.orchestrator.skill_agents.base import TELEGRAM_FORMAT, SkillAgentBase

_SYSTEM_PROMPT = (
    "You are SchoolAI's homework assistant for Ecuadorian teachers.\n"
    "Today is {today}.\n"
    "\n"
    "INSTRUCTIONS:\n"
    "- Focus ONLY on homework and assignment tasks: recording, querying, and deleting assignments.\n"
    "- Ignore any parts of the teacher's message that are about attendance, payments, "
    "or other topics.\n"
    "- If the teacher mentions an education level (bachillerato, egb, básica, inicial) "
    "without the exact course code, call 'listar_cursos' first, then proceed.\n"
    "- Use 'crear_tarea' to record a new homework assignment, test, quiz, or evaluation. "
    "Include all subjects mentioned (materias field accepts a list).\n"
    "- Use 'consultar_tareas' to query recorded assignments for one or more courses.\n"
    "- Use 'eliminar_tarea' to delete a homework assignment. "
    "IMPORTANT: before calling this tool, show the task description and ask the teacher "
    "to confirm the deletion. Only call 'eliminar_tarea' after explicit confirmation.\n"
    "- Always reply in Spanish, concisely.\n"
    "- Never invent homework descriptions or course names."
    + TELEGRAM_FORMAT
)


class HomeworkAgent(SkillAgentBase):
    """Agente especializado en registro y consulta de tareas."""

    name = "homework"
    system_prompt_template = _SYSTEM_PROMPT

    @property
    def tools(self):
        from schoolai.skills.orchestrator.tools import TOOLS_BY_NAME
        return [
            TOOLS_BY_NAME["crear_tarea"],
            TOOLS_BY_NAME["consultar_tareas"],
            TOOLS_BY_NAME["eliminar_tarea"],
            TOOLS_BY_NAME["listar_cursos"],
        ]

    async def _execute_tool(self, name: str, args: dict) -> str:
        from schoolai.skills.orchestrator.tools import execute_tool
        return await execute_tool(name, args)
