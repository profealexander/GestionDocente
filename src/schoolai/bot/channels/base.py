"""Canal de mensajería — interfaz base.

Patrón inspirado en NanoBot (HKUDS/nanobot): cada canal implementa BaseChannel
y convierte sus mensajes entrantes a InboundMessage para el dispatcher.

Esto desacopla la lógica de skills del transporte concreto (Telegram, WhatsApp, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class InboundMessage:
    """Mensaje entrante normalizado, independiente del canal."""

    channel: str  # "telegram" | "whatsapp"
    user_id: int  # ID del docente (telegram_id o teacher.id para WhatsApp-only)
    chat_id: int  # Telegram: chat_id real; WhatsApp: mismo que user_id
    text: str

    @property
    def session_key(self) -> str:
        """Clave única de sesión para aislar estado por canal + chat."""
        return f"{self.channel}:{self.chat_id}"


class BaseChannel(ABC):
    """Contrato mínimo que todo canal debe implementar."""

    name: str  # "telegram" | "whatsapp"

    @abstractmethod
    async def send_text(self, chat_id: int | str, text: str) -> None:
        """Envía texto plano al destinatario."""

    @abstractmethod
    async def send_document(
        self,
        chat_id: int | str,
        data: bytes,
        filename: str,
        caption: str = "",
    ) -> None:
        """Envía un documento (PDF, etc.) al destinatario."""
