"""
Executor — Python puro, sin LLM.
Ejecuta cada PlanStep llamando al DomainController correspondiente.
"""
from __future__ import annotations

from loguru import logger

from .domains.base import BaseDomainController
from .schemas import ActionResult, PlanStep


async def execute(
    steps: list[PlanStep],
    controller: BaseDomainController,
    user_id: str,
) -> list[ActionResult]:
    results: list[ActionResult] = []

    for step in steps:
        try:
            output = await controller.execute_tool(step.tool, step.params, user_id)
            results.append(ActionResult(tool=step.tool, params=step.params, output=output))
            logger.debug(f"[executor] {step.tool}({step.params}) → {output[:80]}")
        except Exception as e:
            logger.error(f"[executor] {step.tool} failed: {e}")
            results.append(
                ActionResult(
                    tool=step.tool,
                    params=step.params,
                    output=f"Error ejecutando {step.tool}: {e}",
                    success=False,
                )
            )

    return results
