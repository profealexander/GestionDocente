"""ContextAgent — gestión de documentos de contexto."""

from __future__ import annotations

from schoolai.skills.orchestrator.skill_agents.base import TELEGRAM_FORMAT, SkillAgentBase

_SYSTEM_PROMPT = (
    "You are SchoolAI's context document manager for Ecuadorian teachers.\n"
    "Today is {today}.\n"
    "\n"
    "INSTRUCTIONS:\n"
    "- Use 'list_context_docs' when the teacher asks what documents they have uploaded.\n"
    "- Use 'search_context' when the teacher asks a question that may be answered by "
    "their uploaded documents (schedule, school calendar, policies, etc.).\n"
    "- Use 'delete_context_doc' to delete a document. Always ask for confirmation first.\n"
    "- Always pass the teacher's Telegram ID exactly as given in the system prompt.\n"
    "- Always reply in Spanish, concisely.\n"
    "- Never invent document content or IDs."
    + TELEGRAM_FORMAT
)


class ContextAgent(SkillAgentBase):
    """Agente especializado en gestión de documentos de contexto."""

    name = "context"
    system_prompt_template = _SYSTEM_PROMPT

    @property
    def tools(self):
        from schoolai.skills.orchestrator.tools import TOOLS_BY_NAME

        return [
            TOOLS_BY_NAME["search_context"],
            TOOLS_BY_NAME["list_context_docs"],
            TOOLS_BY_NAME["delete_context_doc"],
        ]

    async def _execute_tool(self, name: str, args: dict) -> str:
        from schoolai.skills.orchestrator.tools import execute_tool

        return await execute_tool(name, args)
