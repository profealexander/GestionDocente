"""LLM router — classifies incoming messages and routes to the correct agent."""

import asyncio
from functools import partial

from loguru import logger
from zhipuai import ZhipuAI

from schoolai.config import settings

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
    if not settings.glm_api_key:
        logger.warning("No GLM API key, defaulting to homework")
        return "homework"

    try:
        client = ZhipuAI(api_key=settings.glm_api_key)

        def _call():
            return client.chat.completions.create(
                model="glm-4.5-air",
                messages=[
                    {"role": "user", "content": CLASSIFIER_PROMPT.format(text=text)},
                ],
                extra_body={"temperature": 0.0},
            )

        response = await asyncio.to_thread(_call)
        result = response.choices[0].message.content.strip().lower()
        if result not in ("attendance", "homework", "chat", "unknown"):
            result = "unknown"
        logger.info(f"[router] '{text[:50]}' → {result}")
        return result
    except Exception as e:
        logger.error(f"Router error: {e}")
        return "unknown"
