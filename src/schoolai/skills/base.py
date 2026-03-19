"""BaseSkill — clase abstracta que toda skill debe implementar."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod


class BaseSkill(ABC):
    """Interfaz mínima que cada skill debe cumplir.

    Atributos de clase a definir en cada subclase:
        intent   — nombre canónico del intent ("attendance", "homework", …)
        keywords — frozenset de tokens normalizados (minúsculas, sin acentos)
                   para detección O(1).  Ver skills/utils/text.py::normalize().
        patterns — lista de re.Pattern compilados para detección secundaria.
    """

    intent: str
    keywords: frozenset[str] = frozenset()
    patterns: list[re.Pattern] = []

    def matches(self, text: str) -> bool:
        """Devuelve True si este skill reconoce el texto.

        Primero comprueba keywords (O(1)), luego patterns (O(k·n)).
        Subclases pueden sobreescribir para lógica más compleja.
        """
        from schoolai.skills.utils.text import normalize

        norm = normalize(text)
        tokens = frozenset(norm.split())
        if tokens & self.keywords:
            return True
        return any(p.search(norm) for p in self.patterns)

    @abstractmethod
    async def handle(self, update, user_id: int, text: str) -> None:
        """Procesa el mensaje y responde al usuario."""
