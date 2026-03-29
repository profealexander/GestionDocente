"""CuotasAgent — skill agent especializado en cuotas y pagos."""

from __future__ import annotations

from schoolai.skills.orchestrator.skill_agents.base import TELEGRAM_FORMAT, SkillAgentBase

_SYSTEM_PROMPT = (
    "You are SchoolAI's fees and payments assistant for Ecuadorian teachers.\n"
    "Today is {today}.\n"
    "\n"
    "INSTRUCTIONS:\n"
    "- Focus ONLY on school fees, activities, and payments.\n"
    "- Ignore any parts of the teacher's message that are about attendance, homework, "
    "or other topics.\n"
    "- Use 'list_activities' to show all active activities before asking the teacher "
    "which one they mean.\n"
    "- Use 'create_activity' to create a new activity or fee "
    "(requires name and amount; course is optional to auto-enroll students).\n"
    "- Use 'activity_status' to query payment status of an activity by name.\n"
    "- Use 'register_payment' to record student payments "
    "(requires names, amount, activity, and course — ask for course if missing).\n"
    "- Use 'list_courses' if the teacher mentions a level without the exact course code.\n"
    "- Always reply in Spanish, concisely.\n"
    "- Never invent student names or payment amounts."
    + TELEGRAM_FORMAT
)


class CuotasAgent(SkillAgentBase):
    """Agente especializado en cuotas, actividades y registro de pagos."""

    name = "cuotas"
    system_prompt_template = _SYSTEM_PROMPT

    @property
    def tools(self):
        from schoolai.skills.orchestrator.tools import TOOLS_BY_NAME
        return [
            TOOLS_BY_NAME["list_activities"],
            TOOLS_BY_NAME["create_activity"],
            TOOLS_BY_NAME["activity_status"],
            TOOLS_BY_NAME["register_payment"],
            TOOLS_BY_NAME["list_courses"],
        ]

    async def _execute_tool(self, name: str, args: dict) -> str:
        from schoolai.skills.orchestrator.tools import execute_tool
        return await execute_tool(name, args)
