"""
Planner — LLM call #1.
Receives TaskSpec + available tools → returns [{tool, params}, ...].
Uses llm_orchestrator (default: kimi-k2-instruct) for reliable JSON tool selection.
"""
from __future__ import annotations

import json

from loguru import logger

from schoolai.config import settings
from schoolai.gateway.schemas import TaskSpec
from schoolai.skills.llm.client import call_with_fallback

from .domains.base import BaseDomainController
from .schemas import AgentContext, PlanStep

_SYSTEM = """
You are a planning assistant for a school management system.

Given a teacher's request and the available tools, return a JSON array of steps to execute.
Each step: {"tool": "<name>", "params": {<key>: <value>}}

Rules:
- Return ONLY a JSON array. No explanation.
- Use only tools from the provided list.
- Minimum steps needed — no redundant calls.
- If the request is conversational (no action needed), return [].

Available tools:
{tools}
"""


async def plan(
    task: TaskSpec,
    controller: BaseDomainController,
    ctx: AgentContext,
) -> list[PlanStep]:
    tools_desc = json.dumps(controller.tools, ensure_ascii=False, indent=2)
    system = _SYSTEM.replace("{tools}", tools_desc)

    messages = [{"role": "system", "content": system}] + list(ctx.history) + [{"role": "user", "content": task.raw_text}]

    response = call_with_fallback(
        primary=settings.llm_orchestrator,
        fallbacks=settings.llm_orchestrator_fallback,
        messages=messages,
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "[]"

    logger.debug(f"[planner] raw={content[:300]}")
    try:
        raw = json.loads(content)
        if isinstance(raw, list):
            # [{"tool": ..., "params": ...}, ...]
            steps_raw = raw
        elif isinstance(raw, dict) and "tool" in raw:
            # Single step: {"tool": ..., "params": ...}
            steps_raw = [raw]
        else:
            # Wrapped: {"steps": [...]} / {"plan": [...]} / {"tools": [...]}
            steps_raw = next((v for v in raw.values() if isinstance(v, list)), [])
        return [PlanStep(**s) for s in steps_raw]
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(f"[planner] JSON parse error: {e} — content={content[:200]}")
        return []
