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
    "without the exact course code, call 'list_courses' first, then proceed.\n"
    "- Use 'create_assignment' to record a new homework assignment, test, quiz, or evaluation. "
    "Include all subjects mentioned (subjects field accepts a list).\n"
    "- Use 'query_assignments' to query recorded assignments for one or more courses.\n"
    "- Use 'delete_assignment' to delete a homework assignment. "
    "IMPORTANT: before calling this tool, show the task description and ask the teacher "
    "to confirm the deletion. Only call 'delete_assignment' after explicit confirmation.\n"
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
            TOOLS_BY_NAME["create_assignment"],
            TOOLS_BY_NAME["query_assignments"],
            TOOLS_BY_NAME["delete_assignment"],
            TOOLS_BY_NAME["list_courses"],
        ]

    async def _execute_tool(self, name: str, args: dict) -> str:
        from schoolai.skills.orchestrator.tools import execute_tool
        return await execute_tool(name, args)
