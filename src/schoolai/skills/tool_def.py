"""ToolDef — definición de tool OpenAI-compatible para LLM tool calling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema — OpenAI-compatible tool format
    fn: Callable  # función async Python

    def to_tool_dict(self) -> dict:
        """Convierte al formato tool definition OpenAI-compatible (Groq, Z.AI, OpenAI, etc.)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
