"""Base class for all Domain Controllers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseDomainController(ABC):
    """
    Each domain exposes a fixed set of tools (max 4).
    The Planner sees only these tools; the Executor calls execute_tool().
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Canonical domain name, e.g. 'attendance'."""

    @property
    @abstractmethod
    def tools(self) -> list[dict]:
        """OpenAI-style tool definitions sent to the Planner."""

    @abstractmethod
    async def execute_tool(self, tool: str, params: dict[str, Any], user_id: str) -> str:
        """Delegates to the corresponding _tools/ function. Returns plain text."""
