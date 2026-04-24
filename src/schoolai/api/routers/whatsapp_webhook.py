"""Webhook Green API — mensajes entrantes de docentes vía WhatsApp.

Configuración en Green API:
  Settings → Webhooks → URL de notificación: https://<host>/webhook/whatsapp
  Activar: "Входящие сообщения" (incomingMessageReceived)

Flujo:
  Docente → WhatsApp → Green API → POST /webhook/whatsapp
    → busca Teacher por whatsapp_phone
    → _dispatch(WhatsAppUpdate, user_id, text)
    → skill responde vía WhatsApp al mismo docente

Requisitos:
  - Teacher.whatsapp_phone configurado en DB para el docente
  - GREEN_API_INSTANCE y GREEN_API_TOKEN en .env
  - Redis recomendado para flujos multi-mensaje (state compartido con canal Telegram)
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from loguru import logger
from sqlalchemy import select

from schoolai.db.connection import get_db_session
from schoolai.db.models.teacher import Teacher

router = APIRouter(prefix="/webhook", tags=["Webhook"])

# ── Registry lazy-init (solo la primera vez que llega un webhook) ─────────────

_registry_ready = False
_registry_lock = asyncio.Lock()


async def _ensure_registry() -> None:
    """Inicializa el SkillRegistry si aún no está registrado (proceso API)."""
    global _registry_ready
    if _registry_ready:
        return

    async with _registry_lock:
        if _registry_ready:
            return

        from schoolai.skills.registry import registry
        from schoolai.skills.utils.courses import load_course_map

        await load_course_map()

        if not registry._skills:
            from importlib.metadata import entry_points as _eps

            skill_classes = [ep.load() for ep in _eps(group="schoolai.skills")]
            for skill_cls in sorted(skill_classes, key=lambda c: getattr(c, "priority", 50)):
                registry.register(skill_cls())

        _registry_ready = True


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request) -> dict:
    """Recibe webhooks de Green API para mensajes entrantes de docentes."""
    try:
        payload = await request.json()
    except Exception as exc:
        logger.warning(f"[wa_webhook] JSON inválido: {exc}")
        return {"status": "error", "detail": "invalid_json"}

    # Solo procesar mensajes de texto entrantes
    if payload.get("typeWebhook") != "incomingMessageReceived":
        return {"status": "ignored"}

    msg_data = payload.get("messageData", {})
    if msg_data.get("typeMessage") != "textMessage":
        return {"status": "ignored"}

    text = msg_data.get("textMessageData", {}).get("textMessage", "").strip()
    sender = payload.get("senderData", {}).get("sender", "")  # "593XXXXXXXXX@c.us"

    if not text or not sender or sender.endswith("@g.us"):
        # Ignorar grupos y mensajes vacíos
        return {"status": "ignored"}

    phone = sender.removesuffix("@c.us")
    if not phone:
        return {"status": "ignored"}

    # Buscar docente por número de WhatsApp
    async with get_db_session() as session:
        teacher = (
            await session.execute(
                select(Teacher).where(
                    Teacher.whatsapp_phone == phone,
                    Teacher.is_active.is_(True),
                ),
            )
        ).scalar_one_or_none()

    if teacher is None:
        logger.warning(f"[wa_webhook] número no registrado: {phone}")
        return {"status": "unknown_sender"}

    # Usar telegram_id si existe (estado compartido entre canales), si no teacher.id
    user_id: int = teacher.telegram_id or teacher.id

    logger.info(f"[wa_webhook] teacher={teacher.id} phone={phone} text={text[:100]}")

    await _ensure_registry()

    from schoolai.bot.channels.whatsapp import WhatsAppUpdate
    from schoolai.bot.handlers import _dispatch

    wa_update = WhatsAppUpdate(phone=phone, user_id=user_id)
    await _dispatch(wa_update, user_id, text)

    return {"status": "ok"}
