"""ChatSkill — fallback de conversación libre con web search (Groq Compound)."""

from __future__ import annotations

import base64
import re

from loguru import logger

from schoolai.skills.base import BaseSkill

# Resolución mínima aceptable para visión (ancho en px).
# Telegram envía múltiples tamaños; elegimos el más pequeño que cumpla el umbral
# para minimizar el payload a OpenRouter sin perder calidad de OCR.
_MIN_VISION_WIDTH = 800


def _pick_photo(photos) -> object:
    """Elige la foto de menor tamaño con ancho >= _MIN_VISION_WIDTH.
    Fallback: la foto más grande si ninguna alcanza el umbral (ej. imágenes pequeñas).
    """
    for p in photos:  # photos viene ordenado por tamaño ascendente
        if p.width >= _MIN_VISION_WIDTH:
            return p
    return photos[-1]


class ChatSkill(BaseSkill):
    """Catch-all: cualquier mensaje que no reconozca otra skill."""

    intent = "chat"
    priority = 100

    keywords: frozenset[str] = frozenset()
    patterns: list[re.Pattern] = []

    def matches(self, text: str) -> bool:
        return False

    async def handle(self, update, user_id: int, text: str) -> None:
        """Enruta a visión si hay foto adjunta, o al agente de texto en streaming."""
        if update.message.photo:
            await self._handle_vision(update, user_id, text)
        else:
            await self._handle_text(update, user_id, text)

    # ── Texto ─────────────────────────────────────────────────────────────────

    async def _handle_text(self, update, user_id: int, text: str) -> None:
        from schoolai.skills.ia.agent import chat

        sent = await update.message.reply_text("...")
        buffer: list[str] = []
        last_len = 0

        async def send_chunk(delta: str) -> None:
            nonlocal last_len
            buffer.append(delta)
            current = "".join(buffer)
            if len(current) - last_len >= 80:
                last_len = len(current)
                try:
                    await sent.edit_text(current)
                except Exception as exc:
                    logger.warning(f"[chat] failed to edit streaming message: {exc}")

        await chat(user_id, text, send_chunk)

        final = "".join(buffer).strip()
        if final:
            try:
                await sent.edit_text(final, parse_mode="HTML")
            except Exception as exc:
                logger.warning(f"[chat] failed to edit final message: {exc}")
                await sent.edit_text(final)  # fallback sin formato si el HTML falla

    # ── Visión ────────────────────────────────────────────────────────────────

    async def _handle_vision(self, update, user_id: int, caption: str) -> None:
        from schoolai.skills.ia.agent import chat_vision

        sent = await update.message.reply_text("🔍 Analizando imagen...")

        photo = _pick_photo(update.message.photo)
        logger.info(f"[chat_vision] foto seleccionada: {photo.width}x{photo.height} ({photo.file_size} bytes)")

        tg_file = await photo.get_file()
        photo_bytes = await tg_file.download_as_bytearray()
        image_b64 = base64.b64encode(photo_bytes).decode()

        buffer: list[str] = []

        async def _collect(chunk: str) -> None:
            buffer.append(chunk)

        await chat_vision(user_id, image_b64, caption, _collect)

        final = "".join(buffer).strip()
        if final:
            try:
                await sent.edit_text(final, parse_mode="HTML")
            except Exception as exc:
                logger.warning(f"[chat] vision HTML parse falló: {exc}")
                await sent.edit_text(final)  # fallback sin formato
