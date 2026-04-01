"""ContextAgent — gestión de documentos de contexto."""

from __future__ import annotations

from schoolai.skills.orchestrator.skill_agents.base import TELEGRAM_FORMAT, SkillAgentBase

_SYSTEM_PROMPT = (
    "You are SchoolAI's context document manager for Ecuadorian teachers.\n"
    "Today is {today}.\n"
    "\n"
    "INSTRUCTIONS:\n"
    "- Use 'list_context_docs' when the teacher asks what documents they have uploaded.\n"
    "- Use 'search_context' FIRST when the teacher asks a question that may be answered by "
    "their uploaded documents (schedule, school calendar, policies, regulations, etc.).\n"
    "- Use 'web_search' ONLY when search_context returns no relevant results. "
    "Show results to the teacher and ask if they want to save any URL.\n"
    "- Use 'save_web_page' to save a URL when the teacher confirms.\n"
    "- Use 'delete_context_doc' to delete a document. Always ask for confirmation first.\n"
    "- Always pass the teacher's Telegram ID exactly as given in the system prompt.\n"
    "- Always reply in Spanish.\n"
    "\n"
    "CRITICAL — EXACTNESS RULES (never break these):\n"
    "- For questions answered by context documents: copy the relevant fragment verbatim. "
    "Do NOT paraphrase, summarize or infer. Answer ONLY with what is explicitly in the document.\n"
    "- If the document does not contain enough information, say: "
    "'El documento no contiene información sobre eso.' Then offer to search the web.\n"
    "- For web search results: present snippets as-is. Never combine or invent information.\n"
    "- Never add, complete or invent data not present in documents or search results.\n"
    "- Always cite the source at the end of your answer (document title or URL)."
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
            TOOLS_BY_NAME["web_search"],
            TOOLS_BY_NAME["save_web_page"],
        ]

    async def _execute_tool(self, name: str, args: dict) -> str:
        from schoolai.skills.orchestrator.tools import execute_tool

        return await execute_tool(name, args)
