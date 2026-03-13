"""Skill IA — general conversation using GLM-4.7 via ZhipuAI SDK."""

import asyncio

from loguru import logger
from zhipuai import ZhipuAI

from schoolai.config import settings
from schoolai.skills.ia import history

SYSTEM_PROMPT = """You are an intelligent school assistant designed to support teachers in their daily work.

Behavior:
- Always respond in Spanish, clearly and concisely
- Adapt your tone: professional but approachable
- Be direct — avoid unnecessary preambles or filler phrases

You can help with:
- Pedagogical questions and teaching strategies
- Lesson planning and activity design
- Academic topic explanations at any level
- Text drafting: emails, reports, rubrics, announcements
- General educational guidance

If the question is outside the educational scope, politely redirect the teacher."""

# Singleton client — created once, reused on every call
_client: ZhipuAI | None = None


def _get_client() -> ZhipuAI:
    global _client
    if _client is None:
        _client = ZhipuAI(api_key=settings.glm_api_key)
    return _client


async def chat(user_id: int, text: str, send_chunk) -> str:
    """Stream response chunks via send_chunk(text) callback.

    Returns the full reply for history storage.
    """
    if not settings.glm_api_key:
        await send_chunk("El servicio de IA no está configurado.")
        return ""

    try:
        history.append(user_id, "user", text)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history.get(user_id)
        client = _get_client()

        def _stream():
            return client.chat.completions.create(
                model=settings.glm_model,
                messages=messages,
                extra_body={"temperature": 0.7},
                stream=True,
            )

        stream = await asyncio.to_thread(_stream)

        full_reply = []
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                full_reply.append(delta)
                await send_chunk(delta)

        reply = "".join(full_reply).strip()
        history.append(user_id, "assistant", reply)
        return reply

    except Exception as e:
        logger.error(f"IA skill error: {e}")
        await send_chunk("Ocurrió un error al procesar tu consulta. Intenta de nuevo.")
        return ""
