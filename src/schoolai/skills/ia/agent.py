"""Skill IA — general conversation."""

import asyncio

from loguru import logger

from schoolai.config import settings
from schoolai.skills.ia import history
from schoolai.skills.llm import get_client, parse_model

SYSTEM_PROMPT = """You are a teaching assistant. Always reply in Spanish, clearly and concisely.

IMPORTANT: You have NO access to school data (students, homework, attendance, grades).
If asked about a specific student, homework report, who was absent, or any school record query, reply:
"Para eso usa el registro directo: dime el curso y te muestro los datos."
Never invent or assume student, course, or homework data."""


async def chat(user_id: int, text: str, send_chunk) -> str:
    """Stream response chunks via send_chunk(text) callback.

    Returns the full reply for history storage.
    """
    provider, model = parse_model(settings.llm_chat)

    try:
        client = get_client(provider, timeout=120.0)
    except ValueError as e:
        await send_chunk("El servicio de IA no está configurado.")
        logger.warning(f"[ia] {e}")
        return ""

    try:
        history.append(user_id, "user", text)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history.get(user_id)

        def _stream():
            return client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                top_p=0.9,
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
        logger.error(f"[ia] error: {e}")
        await send_chunk("Ocurrió un error al procesar tu consulta. Intenta de nuevo.")
        return ""
