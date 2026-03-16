"""LLM router — classifies incoming messages and routes to the correct agent."""

import asyncio

from loguru import logger

from schoolai.config import settings
from schoolai.skills.llm import get_client, parse_model

CLASSIFIER_PROMPT = """Classify the following teacher message into exactly one word:

- attendance → records who was absent, late, or justified (faltó, faltaron, atraso, tardanza, justificado, no vino, etc.)
- homework   → registers a task, assignment, activity, project, exam, or evaluation
- chat       → greeting, question, general inquiry, or any other conversation
- unknown    → completely unclear intent

Rules: reply with ONE word only, no punctuation, no explanation.
Messages are in Spanish and may have typos (e.g. "faltaon" = "faltaron", "hot" = "hoy").

Message: "{text}"
Classification:"""


async def classify(text: str) -> str:
    provider, model = parse_model(settings.llm_router)

    try:
        client = get_client(provider, timeout=30.0)
    except ValueError as e:
        logger.warning(f"[router] {e}, defaulting to unknown")
        return "unknown"

    try:
        def _call():
            return client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": CLASSIFIER_PROMPT.format(text=text)}],
                temperature=0.0,
                max_tokens=10,
            )

        response = await asyncio.to_thread(_call)
        result = (response.choices[0].message.content or "").strip().lower()
        if result not in ("attendance", "homework", "chat", "unknown"):
            result = "unknown"
        logger.info(f"[router] '{text[:50]}' → {result}")
        return result
    except Exception as e:
        logger.error(f"[router] error: {e}")
        return "unknown"
