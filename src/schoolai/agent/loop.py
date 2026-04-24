"""
Agent Loop — ciclo principal que coordina todo.

TaskSpec → Router → Planner (LLM#1) → Executor → Synthesizer (LLM#2) → AgentResponse
"""
from __future__ import annotations

import time

from loguru import logger

from schoolai.gateway.schemas import TaskSpec

from . import context as ctx_engine
from .executor import execute
from .orchestrator import route
from .planner import plan
from .schemas import AgentResponse
from .synthesizer import synthesize


async def run(task: TaskSpec) -> AgentResponse:
    t0 = time.monotonic()

    # 1. Load context
    ctx = ctx_engine.load(task.user_id, task.session_id)

    # 2. Route to domain controller (Python pure)
    controller = route(task)
    logger.debug(f"[loop] domain={task.domain} controller={controller.name}")

    # 3. Plan — LLM call #1
    steps = await plan(task, controller, ctx)
    logger.debug(f"[loop] plan={[s.tool for s in steps]}")

    # 4. Execute — Python pure
    results = await execute(steps, controller, task.user_id)

    # 5. Synthesize — LLM call #2
    response_text = await synthesize(task, results, ctx)

    # 6. Persist context
    ctx_engine.save(ctx, task.raw_text, response_text)

    elapsed = time.monotonic() - t0
    logger.info(
        f"[loop] done in {elapsed:.2f}s — "
        f"domain={task.domain} intent={task.intent} steps={len(steps)}"
    )

    return AgentResponse(
        text=response_text,
        domain=task.domain,
        intent=task.intent,
        steps=results,
    )
