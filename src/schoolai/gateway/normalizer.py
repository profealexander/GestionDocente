"""
Converts a raw MessageSpec into a TaskSpec.
Domain/intent classification is done via Structured Output LLM (router.py).
"""
from __future__ import annotations

from .router import classify
from .schemas import MessageSpec, TaskSpec


async def normalize(msg: MessageSpec) -> TaskSpec:
    classification = await classify(msg.text)
    return TaskSpec(
        channel=msg.channel,
        domain=classification["domain"],
        intent=classification["intent"],
        entities=classification["entities"],
        raw_text=msg.text,
        user_id=msg.user_id,
        session_id=msg.session_id,
    )
