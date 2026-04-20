"""Skill IA — general conversation.

Routing:
  - qwen3-32b (llm_chat_fallback) como modelo por defecto — 1038ms, 100% noex, Groq free.
  - compound-beta (llm_chat) solo cuando el mensaje contiene señales de búsqueda web
    (noticias, precio, clima, resultados, eventos recientes, etc.).
"""

import asyncio
import re
from datetime import date

from loguru import logger

from schoolai.config import settings
from schoolai.skills.ia import history
from schoolai.skills.llm import get_client, parse_model

# Palabras que indican que el usuario necesita información en tiempo real de la web.
_WEB_RE = re.compile(
    r"\b(noticia[s]?|precio[s]?|clima|cotizaci[oó]n|resultado[s]?|partido[s]?|"
    r"qui[eé]n gan[oó]|[uú]ltim[ao][s]?|reciente[s]?|hoy en d[ií]a|"
    r"actualmente|en este momento|busca|buscar|busca en|busca en internet|"
    r"qu[eé] pas[oó]|novedades|tendencia[s]?|evento[s]?|estreno[s]?)\b",
    re.I,
)


def _needs_web(text: str) -> bool:
    """True si el texto contiene señales de búsqueda web en tiempo real."""
    return bool(_WEB_RE.search(text))

SYSTEM_PROMPT = """I am an AI model. Today is {today}.

Always reply in Spanish. Be clear and concise.
Format your response using Telegram HTML tags only: <b>bold</b>, <i>italic</i>, <code>inline code</code>, <pre>code block</pre>.
Do NOT use markdown (no **, no _, no #). Only use the HTML tags listed above.
If the question requires current or real-time information, search the web before answering.

You have NO access to institutional data (students, attendance, homework, grades).
If asked about specific student records, reply:
"Para eso escríbeme el curso directamente."
Never invent student names, grades, or attendance data."""


def _providers_chain(web: bool = False) -> list[tuple[str, str]]:
    """Retorna lista de (provider, model) a intentar en orden.

    web=True  → compound-beta primero (búsqueda web nativa), fallback a mistral-small.
    web=False → mistral-small primero (882ms), fallback a compound-beta si falla.
    """
    primary = settings.llm_chat          # compound-beta
    fallback = settings.llm_chat_fallback  # mistral-small-latest

    if web:
        chain = [primary]
        if fallback:
            chain += [m.strip() for m in fallback.split(",") if m.strip()]
    else:
        chain = []
        if fallback:
            chain += [m.strip() for m in fallback.split(",") if m.strip()]
        chain.append(primary)  # compound-beta como último recurso si mistral falla

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

    Ruta por defecto: mistral-small (882ms).
    Ruta web: compound-beta (6337ms) cuando el texto pide información en tiempo real.
    Returns the full reply for history storage.
    """
    history.append(user_id, "user", text)
    system = SYSTEM_PROMPT.format(today=date.today().strftime("%A, %B %d %Y"))
    messages = [{"role": "system", "content": system}] + history.get(user_id)

    web = _needs_web(text)
    if web:
        logger.debug(f"[ia] ruta web activa para: {text[:60]!r}")
    chain = _providers_chain(web=web)
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


async def chat_vision(user_id: int, image_b64: str, caption: str, send_chunk) -> str:
    """Procesa una imagen con un modelo de visión (OpenRouter free tier).

    Cadena de modelos configurada en settings.llm_vision / settings.llm_vision_fallback.
    No hace streaming — envía la respuesta completa de una vez vía send_chunk().
    """
    from schoolai.skills.llm.usage import fire_record_usage

    system = SYSTEM_PROMPT.format(today=date.today().strftime("%A, %B %d %Y"))
    text_prompt = caption.strip() if caption else "Describe lo que ves en esta imagen y extrae cualquier información relevante."

    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ],
        },
    ]

    vision_models = [settings.llm_vision]
    if settings.llm_vision_fallback:
        vision_models += [m.strip() for m in settings.llm_vision_fallback.split(",") if m.strip()]

    for pm in vision_models:
        provider, model = parse_model(pm)
        try:
            client = get_client(provider, timeout=30.0)
        except ValueError as e:
            logger.warning(f"[ia_vision] provider {provider!r} no configurado: {e}")
            continue

        try:
            logger.info(f"[ia_vision] usando {provider}/{model}")

            def _call(p=provider, m=model, msgs=messages):
                return client.chat.completions.create(
                    model=m,
                    messages=msgs,
                    max_tokens=1024,
                    temperature=0.4,
                )

            response = await asyncio.to_thread(_call)
            reply = response.choices[0].message.content.strip()

            fire_record_usage(provider=provider, model=model, response=response, agent="ia_vision")

            history.append(user_id, "user", f"[imagen] {text_prompt}")
            history.append(user_id, "assistant", reply)

            await send_chunk(reply)
            return reply

        except Exception as e:
            logger.warning(f"[ia_vision] {provider}/{model} falló: {e} — intentando siguiente")
            continue

    reply = "No pude procesar la imagen. Intenta de nuevo."
    await send_chunk(reply)
    return reply
