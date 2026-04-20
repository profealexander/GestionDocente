"""
Thin Telegram adapter for Gateway v2.

When GATEWAY_ENABLED=true, called from handle_text before v1 dispatch.
Normalizes the message to a TaskSpec via the gateway (same process, no HTTP).
The TaskSpec is stored in context.user_data["task_spec"] for downstream use.
v1 dispatch continues unchanged — no behavior change in Fase 1.
"""
from __future__ import annotations

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from schoolai.gateway.normalizer import normalize
from schoolai.gateway.schemas import MessageSpec
from schoolai.gateway.session import get_session_id


async def intercept(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    user_id = str(update.effective_user.id)
    session_id = get_session_id(user_id, "telegram")

    msg = MessageSpec(
        channel="telegram",
        user_id=user_id,
        session_id=session_id,
        text=text,
    )
    task = await normalize(msg)

    context.user_data["task_spec"] = task.model_dump()
    logger.debug(
        f"[gateway] TaskSpec — domain={task.domain} intent={task.intent} "
        f"entities={task.entities} session={session_id}"
    )
