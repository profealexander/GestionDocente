"""
Synthesizer — LLM call #2.
Receives ActionResults + original request → formatted response in Spanish.
Uses llm_router (gemini-flash-lite) — fast, cheap, good at formatting.
"""
from __future__ import annotations

from loguru import logger

from schoolai.config import settings
from schoolai.gateway.schemas import TaskSpec
from schoolai.skills.llm.client import call_with_fallback

from .schemas import ActionResult, AgentContext

_SYSTEM = """
You are a concise assistant for a school teacher. Reply in Spanish.
Summarize the results of the actions taken. Be brief and direct.
Use plain text — no markdown headers, minimal formatting.
If there are no results, respond naturally to the teacher's message.
"""


async def synthesize(
    task: TaskSpec,
    results: list[ActionResult],
    ctx: AgentContext,
) -> str:
    if not results:
        # No tool calls — pure conversational response
        results_text = "(sin acciones)"
    else:
        results_text = "\n".join(
            f"[{r.tool}]: {r.output}" for r in results
        )

    user_content = (
        f"Mensaje del docente: {task.raw_text}\n\n"
        f"Resultados de las acciones:\n{results_text}"
    )

    messages = list(ctx.history) + [{"role": "user", "content": user_content}]

    try:
        response = await call_with_fallback(
            primary=settings.llm_synthesizer,
            fallbacks=settings.llm_synthesizer_fallback,
            messages=[{"role": "system", "content": _SYSTEM}] + messages,
            temperature=0.3,
            max_tokens=512,
        )
        return response.choices[0].message.content or ""
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"[synthesizer] LLM error: {e}")
        if results:
            return results[0].output
        return "No pude procesar tu solicitud."
