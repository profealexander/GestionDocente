"""Tool de Python REPL."""

from __future__ import annotations

from schoolai.skills.orchestrator.repl import run_repl


async def _python_repl(code: str) -> str:
    """Executes restricted Python code with read-only DB access."""
    return await run_repl(code)
