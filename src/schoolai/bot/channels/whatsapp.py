"""Canal WhatsApp bidireccional — Green API.

Convierte mensajes entrantes de docentes vía WhatsApp en objetos compatibles
con el dispatcher existente, sin modificar ningún skill handler.

Patrón Adapter: WhatsAppUpdate duck-typea telegram.Update para que
_dispatch() y todos los skills funcionen sin cambios.

Conversión de formato:
  HTML (Telegram) → WhatsApp markdown
  InlineKeyboardMarkup → lista numerada en texto plano

Limitaciones de fase 1:
  - Los flujos multi-paso que requieren botones inline no funcionan en WhatsApp.
  - El estado compartido entre Telegram y WhatsApp requiere Redis configurado.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from loguru import logger

from schoolai.bot.channels.base import BaseChannel
from schoolai.config import settings
from schoolai.skills.whatsapp.sender import send_whatsapp, send_whatsapp_pdf

# ── Conversión de formato HTML → WhatsApp markdown ────────────────────────────

_CONVERSIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"<b>(.*?)</b>",   re.DOTALL), r"*\1*"),
    (re.compile(r"<strong>(.*?)</strong>", re.DOTALL), r"*\1*"),
    (re.compile(r"<i>(.*?)</i>",   re.DOTALL), r"_\1_"),
    (re.compile(r"<em>(.*?)</em>", re.DOTALL), r"_\1_"),
    (re.compile(r"<code>(.*?)</code>", re.DOTALL), r"`\1`"),
    (re.compile(r"<pre>(.*?)</pre>",   re.DOTALL), r"```\1```"),
    (re.compile(r"<br\s*/?>"),     "\n"),
    (re.compile(r"<[^>]+>"),       ""),   # elimina cualquier otra etiqueta
]


def _html_to_wa(text: str) -> str:
    """Convierte HTML de Telegram a formato WhatsApp."""
    for pattern, replacement in _CONVERSIONS:
        text = pattern.sub(replacement, text)
    return text.strip()


def _keyboard_to_text(markup) -> str:
    """Convierte InlineKeyboardMarkup en lista numerada de texto."""
    try:
        lines: list[str] = []
        n = 1
        for row in markup.inline_keyboard:
            for btn in row:
                lines.append(f"{n}. {btn.text}")
                n += 1
        return ("\n\n" + "\n".join(lines)) if lines else ""
    except Exception:
        return ""


# ── Adapter: duck-typea telegram.Message ──────────────────────────────────────

class _WhatsAppMessage:
    """Duck-typea telegram.Message para que skills existentes funcionen sin cambios."""

    def __init__(self, phone: str) -> None:
        self._phone = phone

    async def reply_text(
        self,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup=None,
        **kwargs,
    ) -> None:
        clean = _html_to_wa(text) if parse_mode else text
        if reply_markup is not None:
            clean += _keyboard_to_text(reply_markup)
        await send_whatsapp(
            settings.green_api_instance,
            settings.green_api_token,
            self._phone,
            clean,
        )

    async def reply_document(
        self,
        document,
        *,
        filename: str = "archivo.pdf",
        caption: str = "",
        **kwargs,
    ) -> None:
        data = document.read() if hasattr(document, "read") else bytes(document)
        await send_whatsapp_pdf(
            settings.green_api_instance,
            settings.green_api_token,
            self._phone,
            data,
            filename,
            caption,
        )


class WhatsAppUpdate:
    """Minimal Telegram Update adapter para mensajes WhatsApp entrantes de docentes.

    Permite llamar a handlers._dispatch(wa_update, user_id, text) sin
    modificar ningún skill handler existente.

    callback_query = None indica que los flows de botones inline no están disponibles
    por este canal — las skills que los usan solo enviarán el texto sin botones.
    """

    def __init__(self, phone: str, user_id: int) -> None:
        self.message = _WhatsAppMessage(phone)
        self.effective_user = SimpleNamespace(
            id=user_id,
            username=phone,
            first_name="",
            is_bot=False,
        )
        self.effective_chat = SimpleNamespace(id=user_id)
        self.callback_query = None


# ── Canal WhatsApp (BaseChannel) ──────────────────────────────────────────────

class WhatsAppChannel(BaseChannel):
    """Canal WhatsApp usando Green API."""

    name = "whatsapp"

    async def send_text(self, chat_id: int | str, text: str) -> None:
        phone = str(chat_id).lstrip("+")
        ok = await send_whatsapp(
            settings.green_api_instance,
            settings.green_api_token,
            phone,
            text,
        )
        if not ok:
            logger.warning(f"[whatsapp] send_text falló para {phone}")

    async def send_document(
        self,
        chat_id: int | str,
        data: bytes,
        filename: str,
        caption: str = "",
    ) -> None:
        phone = str(chat_id).lstrip("+")
        ok = await send_whatsapp_pdf(
            settings.green_api_instance,
            settings.green_api_token,
            phone,
            data,
            filename,
            caption,
        )
        if not ok:
            logger.warning(f"[whatsapp] send_document falló para {phone}")
