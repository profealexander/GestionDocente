"""Retrocompatibilidad — re-exports desde bot.action package."""

from schoolai.bot.action import (  # noqa: F401
    handle_act_callback,
    handle_act_confirm_callback,
    handle_course_action_callback,
    handle_extraction,
    handle_selection_callback,
    pop_pending,
    resolve_selection_text,
    store_pending,
)
