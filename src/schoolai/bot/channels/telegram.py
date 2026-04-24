"""Canal Telegram — wrapper de BaseChannel sobre el bot existente.

No reemplaza la lógica actual de main.py; solo expone la misma funcionalidad
como BaseChannel para uniformidad con el canal WhatsApp.

El bot real sigue arrancando con bot/main.py → run().
"""

from __future__ import annotations

from schoolai.bot.channels.base import BaseChannel


class TelegramChannel(BaseChannel):
    """Canal Telegram implementado con python-telegram-bot."""

    name = "telegram"

    def __init__(self, bot) -> None:
        self._bot = bot  # telegram.Bot instance

    async def send_text(self, chat_id: int | str, text: str) -> None:
        await self._bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    async def send_document(
        self,
        chat_id: int | str,
        data: bytes,
        filename: str,
        caption: str = "",
    ) -> None:
        from io import BytesIO

        await self._bot.send_document(
            chat_id=chat_id,
            document=BytesIO(data),
            filename=filename,
            caption=caption,
        )
