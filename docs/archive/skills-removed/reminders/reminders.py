"""RemindersAgent — skill agent para recordatorios programados."""

from __future__ import annotations

from schoolai.skills.orchestrator.skill_agents.base import TELEGRAM_FORMAT, SkillAgentBase

_SYSTEM_PROMPT = (
    "You are SchoolAI's reminders assistant for Ecuadorian teachers.\n"
    "Today is {today}.\n"
    "\n"
    "INSTRUCTIONS:\n"
    "- Focus ONLY on scheduling and managing reminders.\n"
    "- Use 'create_reminder' to schedule a new reminder.\n"
    "  - target='teacher' sends a Telegram message to the teacher at the scheduled time.\n"
    "  - target='parents' sends a WhatsApp message to all parents of the given course.\n"
    "  - target='both' sends to both channels.\n"
    "  - 'course' is required when target is 'parents' or 'both'. "
    "Call 'list_courses' first if the teacher gives a level name (bachillerato, egb) "
    "without the exact course code.\n"
    "  - scheduled_at must be ISO 8601 (YYYY-MM-DDTHH:MM:SS). "
    "Infer the date from context (e.g. 'mañana' = today+1, 'el viernes' = next Friday).\n"
    "- Use 'list_reminders' to show the teacher's reminders.\n"
    "- Use 'cancel_reminder' to cancel a pending reminder by ID.\n"
    "- Always pass the teacher's Telegram ID exactly as given in the system prompt.\n"
    "- Always reply in Spanish, concisely.\n"
    "- Never invent course names or reminder IDs."
    + TELEGRAM_FORMAT
)


class RemindersAgent(SkillAgentBase):
    """Agente especializado en recordatorios programados."""

    name = "reminders"
    system_prompt_template = _SYSTEM_PROMPT

    @property
    def tools(self):
        from schoolai.skills.orchestrator.tools import TOOLS_BY_NAME

        return [
            TOOLS_BY_NAME["create_reminder"],
            TOOLS_BY_NAME["list_reminders"],
            TOOLS_BY_NAME["cancel_reminder"],
            TOOLS_BY_NAME["list_courses"],
        ]

    async def _execute_tool(self, name: str, args: dict) -> str:
        from schoolai.skills.orchestrator.tools import execute_tool

        return await execute_tool(name, args)
