"""ContextAgent — gestión de documentos de contexto."""

from __future__ import annotations

import contextvars

from loguru import logger

from schoolai.config import settings
from schoolai.skills.orchestrator.skill_agents.base import TELEGRAM_FORMAT, SkillAgentBase

# ContextVar aísla el valor por tarea asyncio — seguro con usuarios concurrentes
_teacher_has_docs_var: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "teacher_has_docs", default=True
)

_COMMON_RULES = (
    "\n"
    "CRITICAL — EXACTNESS RULES (never break these):\n"
    "- For web search results: present snippets as-is. Never combine or invent information.\n"
    "- Never add, complete or invent data not present in search results.\n"
    "- Always cite the source at the end of your answer (document title or URL)."
    + TELEGRAM_FORMAT
)

# Prompt cuando el docente SÍ tiene documentos cargados
_SYSTEM_PROMPT_WITH_DOCS = (
    "You are SchoolAI's context document manager for Ecuadorian teachers.\n"
    "Today is {today}.\n"
    "\n"
    "INSTRUCTIONS:\n"
    "- Use 'list_context_docs' ONLY when the teacher explicitly asks what documents they have uploaded.\n"
    "- Use 'search_context' once when the teacher asks a question that may be answered by "
    "their uploaded documents (schedule, school calendar, policies, regulations, etc.).\n"
    "- If 'search_context' returns no results, call 'web_search' IMMEDIATELY — do NOT call "
    "'search_context' or 'list_context_docs' again.\n"
    "- Use 'web_search' with a specific, date-aware query (include the current year).\n"
    "- Use 'save_web_page' to save a URL when the teacher confirms.\n"
    "- Use 'delete_context_doc' to delete a document. Always ask for confirmation first.\n"
    "- Always pass the teacher's Telegram ID exactly as given in the system prompt.\n"
    "- Always reply in Spanish.\n"
    + _COMMON_RULES
)

# Prompt cuando NO hay documentos — solo web_search disponible
_SYSTEM_PROMPT_NO_DOCS = (
    "You are SchoolAI, an assistant for Ecuadorian teachers.\n"
    "Today is {today}.\n"
    "\n"
    "INSTRUCTIONS:\n"
    "- The teacher has no uploaded documents. Your only tool is 'web_search'.\n"
    "- Use 'web_search' immediately with a specific, date-aware query (include year and country 'Ecuador').\n"
    "- Use 'save_web_page' to save a URL if the teacher wants to keep it for future reference.\n"
    "- Always reply in Spanish.\n"
    + _COMMON_RULES
)

# Tools disponibles cuando el docente SÍ tiene documentos cargados
_TOOLS_WITH_DOCS = ["search_context", "list_context_docs", "delete_context_doc", "web_search", "save_web_page"]
# Tools cuando NO hay documentos — salta directo a web_search
_TOOLS_NO_DOCS = ["web_search", "save_web_page"]


class ContextAgent(SkillAgentBase):
    """Agente especializado en gestión de documentos de contexto.

    Optimizaciones:
    - llm_override: usa qwen3-32b (Groq, rápido) en vez de DeepSeek (~5-7s)
    - Pre-check de docs: si el docente no tiene documentos, excluye search_context y
      list_context_docs, y usa un system prompt simplificado — reduce de 3 a 2 llamadas LLM.
    """

    name = "context"
    system_prompt_template = _SYSTEM_PROMPT_WITH_DOCS  # default; se sobreescribe en run()
    llm_override = settings.llm_context_agent

    @property
    def tools(self):
        from schoolai.skills.orchestrator.tools import TOOLS_BY_NAME

        names = _TOOLS_WITH_DOCS if _teacher_has_docs_var.get() else _TOOLS_NO_DOCS
        return [TOOLS_BY_NAME[n] for n in names]

    def get_system_prompt(self) -> str:
        from datetime import date
        template = _SYSTEM_PROMPT_WITH_DOCS if _teacher_has_docs_var.get() else _SYSTEM_PROMPT_NO_DOCS
        return template.format(today=date.today().isoformat())  # noqa: DTZ011

    async def _execute_tool(self, name: str, args: dict) -> str:
        from schoolai.skills.orchestrator.tools import execute_tool

        return await execute_tool(name, args)

    async def _check_has_docs(self, teacher_id: int) -> bool:
        """True si el docente tiene al menos un documento de contexto (personal o institucional)."""
        try:
            from sqlalchemy import func, or_, select

            from schoolai.db.connection import get_db_session
            from schoolai.db.models.context_document import ContextDocument
            from schoolai.db.models.teacher import Teacher

            async with get_db_session() as db:
                teacher = (
                    await db.execute(select(Teacher).where(Teacher.telegram_id == teacher_id))
                ).scalar_one_or_none()
                if not teacher:
                    return False

                count = (
                    await db.execute(
                        select(func.count()).select_from(ContextDocument).where(
                            or_(
                                ContextDocument.teacher_id == teacher.id,
                                ContextDocument.scope == "institution",
                            )
                        )
                    )
                ).scalar_one()
                return count > 0

        except Exception as e:  # noqa: BLE001
            logger.warning(f"[context] error verificando docs: {e} — asumiendo sin docs")
            return False

    async def run(
        self,
        text: str,
        prior_messages: list[dict] | None = None,
        teacher_id: int | None = None,
    ) -> str:
        has_docs = await self._check_has_docs(teacher_id) if teacher_id else False
        _teacher_has_docs_var.set(has_docs)
        logger.debug(f"[context] teacher={teacher_id} has_docs={has_docs}")

        return await super().run(text, prior_messages, teacher_id)
