"""Unified tools for OrchestratorSkill.

Each tool is an async function that:
  - manages its own DB session
  - returns plain text for LLM consumption (no HTML)
  - is available via tool calling (OpenAI-compatible format)

Implementations live in _tools/; this module owns the registry and dispatcher.
"""

from __future__ import annotations

from loguru import logger

from schoolai.skills.tool_def import ToolDef
from schoolai.skills.orchestrator._tools.attendance import _query_attendance, _record_attendance
from schoolai.skills.orchestrator._tools.context_docs import (
    _delete_context_doc,
    _list_context_docs,
    _save_web_page,
    _search_context,
    _web_search,
)
from schoolai.skills.orchestrator._tools.courses import _list_courses

from schoolai.skills.orchestrator._tools.homework import (
    _create_assignment,
    _delete_assignment,
    _query_assignments,
)
from schoolai.skills.orchestrator._tools.teacher import _my_courses, _my_schedule

# Re-export helpers for legacy callers that may import from tools directly
from schoolai.skills.orchestrator._tools.helpers import (  # noqa: F401
    _parse_date,
    _period_to_dates,
    _strip_tags,
    _today,
)

TOOLS: list[ToolDef] = [
    ToolDef(
        name="record_attendance",
        description=(
            "Records absences, tardiness, or justified absences for students in a course. "
            "Use status='all_present' if all students attended."
        ),
        parameters={
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Last names or first names of the absent/late students",
                },
                "course": {
                    "type": "string",
                    "description": "Course abbreviation, e.g.: 3bt, 8egb, prep",
                },
                "date": {
                    "type": "string",
                    "description": "today, yesterday, or YYYY-MM-DD. Default: today",
                },
                "status": {
                    "type": "string",
                    "enum": ["absent", "late", "justified", "all_present"],
                    "description": (
                        "absent=missed class, late=tardy, "
                        "justified=excused absence, all_present=everyone attended"
                    ),
                },
                "telegram_id": {
                    "type": "integer",
                    "description": "Telegram ID of the teacher making the record (injected automatically)",
                },
            },
            "required": ["names", "course", "telegram_id"],
        },
        fn=_record_attendance,
    ),
    ToolDef(
        name="query_attendance",
        description="Queries the attendance record for one or more courses.",
        parameters={
            "type": "object",
            "properties": {
                "courses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Course abbreviations, e.g.: ['3bt', '8egb']",
                },
                "period": {
                    "type": "string",
                    "description": "today, yesterday, week, month, trimestre. Default: today",
                },
            },
            "required": ["courses"],
        },
        fn=_query_attendance,
    ),
    ToolDef(
        name="create_assignment",
        description=(
            "Records a new homework assignment, task, or activity for a course. "
            "Only subjects in the teacher's own schedule are allowed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "Teacher's Telegram ID (use exactly the value from the system prompt)",
                },
                "description": {
                    "type": "string",
                    "description": "Full description of the homework or assignment",
                },
                "course": {"type": "string", "description": "Course abbreviation, e.g.: 3bt"},
                "subjects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of subjects. If the teacher names several subjects separated "
                        "by '/' or ',', split them into individual items. "
                        "Use the full subject name as the teacher wrote it. Optional."
                    ),
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date YYYY-MM-DD. Optional.",
                },
            },
            "required": ["telegram_id", "description", "course"],
        },
        fn=_create_assignment,
    ),
    ToolDef(
        name="query_assignments",
        description=(
            "Queries the recorded homework assignments for one or more courses. "
            "Only shows assignments for the teacher's own subjects."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "Teacher's Telegram ID (use exactly the value from the system prompt)",
                },
                "courses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Course abbreviations",
                },
                "period": {
                    "type": "string",
                    "description": "today, yesterday, week, month, trimestre. Default: trimestre",
                },
            },
            "required": ["telegram_id", "courses"],
        },
        fn=_query_assignments,
    ),
    ToolDef(
        name="delete_assignment",
        description=(
            "Permanently deletes a homework assignment by its sequence number and course. "
            "Only call this after the teacher has explicitly confirmed the deletion."
        ),
        parameters={
            "type": "object",
            "properties": {
                "number": {
                    "type": "integer",
                    "description": "Homework sequence number shown in the list, e.g.: 2",
                },
                "course": {
                    "type": "string",
                    "description": "Course abbreviation, e.g.: 1bt",
                },
            },
            "required": ["number", "course"],
        },
        fn=_delete_assignment,
    ),
    ToolDef(
        name="list_courses",
        description=(
            "Lists all available courses with their abbreviations. "
            "Call this BEFORE query_attendance or query_assignments when the teacher "
            "mentions a generic level (bachillerato, egb, básica, inicial) without giving "
            "the exact course code."
        ),
        parameters={
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "enum": ["bachillerato", "egb", "inicial"],
                    "description": (
                        "Education level to filter: 'bachillerato', 'egb' (basic), 'inicial'. "
                        "Omit to list all courses."
                    ),
                },
            },
            "required": [],
        },
        fn=_list_courses,
    ),
    ToolDef(
        name="my_courses",
        description=(
            "Returns the current teacher's assigned courses and subjects. "
            "Call this when the teacher asks about their own courses, subjects, or grades. "
            "Pass the teacher's Telegram ID exactly as given in the system prompt."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
            },
            "required": ["telegram_id"],
        },
        fn=_my_courses,
    ),
    ToolDef(
        name="my_schedule",
        description=(
            "Returns the current teacher's weekly schedule, optionally filtered by day. "
            "Call this when the teacher asks about their schedule or timetable. "
            "Pass the teacher's Telegram ID exactly as given in the system prompt."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "day": {
                    "type": "string",
                    "description": (
                        "Day filter in Spanish or English: lunes, martes, miércoles, "
                        "jueves, viernes. Omit for full week."
                    ),
                },
            },
            "required": ["telegram_id"],
        },
        fn=_my_schedule,
    ),
    ToolDef(
        name="search_context",
        description=(
            "Searches the teacher's context documents (personal and institutional) "
            "using full-text search. Call this when answering questions that may require "
            "information the teacher previously uploaded (schedule, school calendar, policies, etc.)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "query": {
                    "type": "string",
                    "description": "The search query in Spanish.",
                },
                "category": {
                    "type": "string",
                    "enum": ["schedule", "calendar", "policies", "contacts", "notes", "other"],
                    "description": "Optional category filter.",
                },
            },
            "required": ["telegram_id", "query"],
        },
        fn=_search_context,
    ),
    ToolDef(
        name="list_context_docs",
        description="Lists the context documents available to the teacher.",
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "category": {
                    "type": "string",
                    "enum": ["schedule", "calendar", "policies", "contacts", "notes", "other"],
                    "description": "Optional category filter.",
                },
                "scope": {
                    "type": "string",
                    "enum": ["personal", "institution"],
                    "description": "Optional scope filter.",
                },
            },
            "required": ["telegram_id"],
        },
        fn=_list_context_docs,
    ),
    ToolDef(
        name="delete_context_doc",
        description="Deletes a context document by its ID. Ask for confirmation before calling.",
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "doc_id": {
                    "type": "integer",
                    "description": "The document ID to delete.",
                },
            },
            "required": ["telegram_id", "doc_id"],
        },
        fn=_delete_context_doc,
    ),
    ToolDef(
        name="web_search",
        description=(
            "Searches the internet via DuckDuckGo. Use when the teacher asks about something "
            "not found in their context documents (regulations, school calendars, general info). "
            "Returns title, snippet and URL for each result. "
            "After showing results, offer to save a relevant URL with save_web_page."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query in the most specific form possible.",
                },
            },
            "required": ["query"],
        },
        fn=_web_search,
    ),
    ToolDef(
        name="save_web_page",
        description=(
            "Downloads a web page or online document and saves it as a context document "
            "for future queries. Use after web_search when the teacher confirms they want "
            "to save a result."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "url": {
                    "type": "string",
                    "description": "The URL to download and save.",
                },
                "hint": {
                    "type": "string",
                    "description": "Optional description to help categorize the document.",
                },
            },
            "required": ["telegram_id", "url"],
        },
        fn=_save_web_page,
    ),
]

TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


async def execute_tool(name: str, args: dict) -> str:
    """Executes a tool by name. Returns string for the LLM."""
    tool = TOOLS_BY_NAME.get(name)
    if not tool or tool.fn is None:
        return f"Tool '{name}' not found."
    try:
        result = await tool.fn(**args)
        return str(result)
    except Exception as e:  # noqa: BLE001
        logger.error(f"[orchestrator] tool={name} error: {e}")
        return f"Error in '{name}': {e}"
