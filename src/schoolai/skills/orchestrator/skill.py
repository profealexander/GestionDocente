"""OrchestratorSkill — agente inteligente con GLM-4.7-Flash (Z.AI) + todas las herramientas.

Actúa como fallback inteligente entre las skills específicas y ChatSkill:
- Skills específicas (Attendance, Homework, etc.) = detección regex/keywords — rápidas
- OrchestratorSkill = fallback con tool calling — entiende intenciones complejas
- ChatSkill = emergencia si Orchestrator no está configurado

Registro: priority=90 (antes de ChatSkill en 100).
matches() = False → excluido de detect_all(), solo activa vía registry.detect() fallback.
"""

from __future__ import annotations

import re

from loguru import logger

from schoolai.skills.base import BaseSkill


class OrchestratorSkill(BaseSkill):
    """Fallback inteligente: GLM-4.7-Flash con todas las herramientas del sistema."""

    intent = "orchestrator"
    priority = 90

    keywords: frozenset[str] = frozenset()
    patterns: list[re.Pattern] = []

    def matches(self, text: str) -> bool:  # noqa: ARG002
        # Nunca aparece en detect_all() ni en el pipeline regex.
        # registry.detect() lo invoca directamente como fallback (antes de ChatSkill).
        return False

    async def handle(self, update, user_id: int, text: str) -> None:
        from schoolai.skills.orchestrator.agent import run

        # Placeholder mientras procesa
        sent = await update.message.reply_text("⏳")

        try:
            reply = await run(user_id, text)
        except Exception as e:
            logger.error(f"[orchestrator] handle error: {e}")
            reply = "Ocurrió un error. Intenta de nuevo."

        if not reply:
            reply = "No pude procesar tu solicitud."

        # Intentar con HTML primero (la respuesta puede incluir markdown del LLM)
        try:
            await sent.edit_text(reply, parse_mode="HTML")
        except Exception as exc:
            logger.warning(
                f"[orchestrator] HTML parse failed for reply, retrying plain text: {exc}"
            )
            try:
                await sent.edit_text(reply)
            except Exception as exc2:
                logger.warning(f"[orchestrator] plain text reply also failed: {exc2}")
