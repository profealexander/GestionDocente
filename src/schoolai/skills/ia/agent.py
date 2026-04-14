"""Skill IA — general conversation with web search (Groq Compound) + fallback."""

import asyncio
from datetime import date

from loguru import logger

from schoolai.config import settings
from schoolai.skills.ia import history
from schoolai.skills.llm import get_client, parse_model

SYSTEM_PROMPT = """I am an AI model. Today is {today}.

Always reply in Spanish. Be clear and concise.
If the question requires current or real-time information, search the web before answering.

You have NO access to institutional data (students, attendance, homework, grades).
If asked about specific student records, reply:
"Para eso escríbeme el curso directamente."
Never invent student names, grades, or attendance data."""


def _providers_chain() -> list[tuple[str, str]]:
    """Retorna lista de (provider, model) a intentar en orden."""
    chain = [settings.llm_chat]
    if settings.llm_chat_fallback:
        chain += [m.strip() for m in settings.llm_chat_fallback.split(",") if m.strip()]
    return [parse_model(pm) for pm in chain]


async def _stream_once(provider: str, model: str, messages: list) -> tuple[str, object]:
    """Intenta streaming con un provider/model. Retorna (full_reply, last_chunk)."""
    from schoolai.skills.llm.usage import fire_record_usage

    client = get_client(provider, timeout=120.0)

    def _call():
        return client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            top_p=0.9,
            stream=True,
        )

    stream = await asyncio.to_thread(_call)
    full_reply: list[str] = []
    last_chunk = None
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full_reply.append(delta)
        last_chunk = chunk

    if last_chunk is not None:
        fire_record_usage(provider=provider, model=model, response=last_chunk, agent="ia_chat")

    return "".join(full_reply).strip(), last_chunk


async def chat(user_id: int, text: str, send_chunk) -> str:
    """Stream response chunks via send_chunk(text) callback.

    Intenta primero groq/compound (búsqueda web nativa).
    Fallback a mistral/mistral-small-latest si compound falla.
    Returns the full reply for history storage.
    """
    history.append(user_id, "user", text)
    system = SYSTEM_PROMPT.format(today=date.today().strftime("%A, %B %d %Y"))
    messages = [{"role": "system", "content": system}] + history.get(user_id)

    chain = _providers_chain()
    last_error: Exception | None = None

    for provider, model in chain:
        try:
            get_client(provider, timeout=120.0)  # valida key antes de intentar
        except ValueError as e:
            logger.warning(f"[ia] provider {provider!r} no configurado, saltando: {e}")
            continue

        try:
            if provider != chain[0][0] or model != chain[0][1]:
                logger.warning(f"[ia] fallback activado → {provider}/{model}")

            # Stream en tiempo real mientras acumulamos para fallback
            client = get_client(provider, timeout=120.0)

            def _call(p=provider, m=model, msgs=messages):
                return client.chat.completions.create(
                    model=m, messages=msgs, temperature=0.7, top_p=0.9, stream=True,
                )

            from schoolai.skills.llm.usage import fire_record_usage
            stream = await asyncio.to_thread(_call)

            full_reply: list[str] = []
            last_chunk = None
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_reply.append(delta)
                    await send_chunk(delta)
                last_chunk = chunk

            if last_chunk is not None:
                fire_record_usage(provider=provider, model=model, response=last_chunk, agent="ia_chat")

            reply = "".join(full_reply).strip()
            history.append(user_id, "assistant", reply)
            return reply

        except Exception as e:
            last_error = e
            logger.warning(f"[ia] {provider}/{model} falló: {e} — intentando siguiente")
            continue

    logger.error(f"[ia] todos los providers fallaron. Último error: {last_error}")
    await send_chunk("Ocurrió un error al procesar tu consulta. Intenta de nuevo.")
    return ""
