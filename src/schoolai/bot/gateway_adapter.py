"""
Thin Telegram adapter for Gateway v2.

When GATEWAY_ENABLED=true, called from handle_text before v1 dispatch.
Normalizes the message via the gateway and handles it with the agent runtime.
Returns True if the gateway handled the message (skips v1 dispatch).
Returns False to fall through to v1 dispatch (e.g. on gateway error).
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
) -> bool:
    user_id = str(update.effective_user.id)
    session_id = get_session_id(user_id, "telegram")

    try:
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

        from schoolai.agent.loop import run as agent_run
        result = await agent_run(task)
        reply = result.text
        await update.message.reply_text(reply)
        return True

    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error(f"[gateway] intercept error: {exc} — falling back to v1 dispatch")
        return False
