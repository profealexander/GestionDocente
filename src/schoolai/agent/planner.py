"""
Planner — LLM call #1.
Receives TaskSpec + available tools → returns [{tool, params}, ...].
Uses llm_orchestrator (Kimi K2) for reliable JSON tool selection.
"""
from __future__ import annotations

import json

from loguru import logger

from schoolai.config import settings
from schoolai.gateway.schemas import TaskSpec
from schoolai.skills.llm.client import get_client, parse_model

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
    system = _SYSTEM.format(tools=tools_desc)

    messages = list(ctx.history) + [{"role": "user", "content": task.raw_text}]

    provider, model = parse_model(settings.llm_orchestrator)
    client = get_client(provider)

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}] + messages,
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "[]"

    try:
        raw = json.loads(content)
        # Model may return {"steps": [...]} or directly [...]
        steps_raw = raw if isinstance(raw, list) else raw.get("steps", [])
        return [PlanStep(**s) for s in steps_raw]
    except Exception as e:
        logger.warning(f"[planner] JSON parse error: {e} — content={content[:200]}")
        return []
