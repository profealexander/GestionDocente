"""ChatSkill — fallback de conversación libre con web search (Groq Compound)."""

from __future__ import annotations

import re

from loguru import logger

from schoolai.skills.base import BaseSkill


class ChatSkill(BaseSkill):
    """Catch-all: cualquier mensaje que no reconozca otra skill."""

    intent = "chat"
    priority = 100

    # Sin keywords ni patterns — nunca se llama matches() en esta skill.
    # El registry la usa como fallback cuando ninguna otra hace match.
    keywords: frozenset[str] = frozenset()
    patterns: list[re.Pattern] = []

    def matches(self, text: str) -> bool:
        # El registry nunca itera hasta aquí; detect() retorna ChatSkill directamente
        # cuando ninguna otra skill hizo match.
        return False

    async def handle(self, update, user_id: int, text: str) -> None:
        """Responde con el agente de IA en modo streaming."""
        from schoolai.bot.handlers import (
            _detect_course_group,
            _detect_course_only,
            _show_course_action_menu,
            _show_course_group_menu,
        )
        from schoolai.bot.mode import is_jornada
        from schoolai.skills.ia.agent import chat
        from schoolai.skills.utils.courses import get_teacher_abbrevs

        # En modo Libre: si el mensaje es solo un nombre de curso → menú de acciones
        # Solo se muestran los cursos asignados al docente (admin ve todos).
        if not is_jornada():
            allowed = await get_teacher_abbrevs(user_id)
            course_info = _detect_course_only(text, allowed)
            if course_info:
                await _show_course_action_menu(update, course_info)
                return

            group_courses = _detect_course_group(text, allowed)
            if group_courses:
                await _show_course_group_menu(update, group_courses)
                return

        sent = await update.message.reply_text("...")
        buffer: list[str] = []
        last_len = 0

        async def send_chunk(delta: str) -> None:
            nonlocal last_len
            buffer.append(delta)
            current = "".join(buffer)
            if len(current) - last_len >= 20:
                last_len = len(current)
                try:
                    await sent.edit_text(current)
                except Exception as exc:
                    logger.warning(f"[chat] failed to edit streaming message: {exc}")

        await chat(user_id, text, send_chunk)

        final = "".join(buffer).strip()
        if final:
            try:
                await sent.edit_text(final)
            except Exception as exc:
                logger.warning(f"[chat] failed to edit final message: {exc}")
