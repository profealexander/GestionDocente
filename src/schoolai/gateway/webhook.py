"""
Webhook Telegram — reemplaza polling.
Telegram POST a /gateway/telegram/{token} → Gateway normaliza → Agent Runtime.

Para registrar el webhook:
    curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
         -d "url=https://<tu-dominio>/gateway/telegram/<TOKEN>"

Para dev local usar ngrok:
    ngrok http 8001
    curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
         -d "url=https://<ngrok-id>.ngrok.io/gateway/telegram/<TOKEN>"
"""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request
from loguru import logger

from schoolai.config import settings

from .normalizer import normalize
from .schemas import MessageSpec
from .session import get_session_id


def _verify_token(token: str) -> str:
    """Returns user-facing bot token if path token matches any configured bot."""
    for bot_token in (
        settings.telegram_bot_token,
        settings.telegram_bot_token_jornada,
        settings.telegram_bot_token_agente,
    ):
        if bot_token and hmac.compare_digest(token, bot_token):
            return bot_token
    raise HTTPException(status_code=403, detail="Invalid webhook token")


async def handle_telegram_webhook(token: str, request: Request) -> dict:
    """
    Receives Telegram Update JSON, extracts text message, runs through Agent Runtime.
    Returns empty dict (Telegram ignores the response body for webhooks).
    """
    _verify_token(token)

    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {}

    text = message.get("text", "").strip()
    if not text:
        return {}

    chat = message.get("chat", {})
    user = message.get("from", {})
    user_id = str(user.get("id", chat.get("id", "unknown")))

    # Auth check
    from .auth import AuthError, check_auth
    try:
        check_auth(user_id)
    except AuthError:
        logger.warning(f"[webhook] unauthorized user_id={user_id}")
        return {}

    session_id = get_session_id(user_id, "telegram")
    msg = MessageSpec(channel="telegram", user_id=user_id, session_id=session_id, text=text)
    task = await normalize(msg)

    from schoolai.agent.loop import run
    result = await run(task)

    # Send reply back via Telegram Bot API
    await _send_reply(token, chat["id"], result.text)
    return {}


async def _send_reply(bot_token: str, chat_id: int, text: str) -> None:
    import httpx
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    except Exception as e:
        logger.error(f"[webhook] send_reply error: {e}")
