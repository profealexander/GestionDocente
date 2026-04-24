"""BaseSkill — clase abstracta que toda skill debe implementar."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from functools import lru_cache

from schoolai.skills.utils.text import normalize


@lru_cache(maxsize=2048)
def _tokenize(norm: str) -> frozenset[str]:
    """Tokeniza texto ya normalizado. Cache LRU: mismos mensajes se repiten."""
    return frozenset(norm.split())


class BaseSkill(ABC):
    """Interfaz mínima que cada skill debe cumplir.

    Atributos de clase a definir en cada subclase:
        intent   — nombre canónico del intent ("attendance", "homework", …)
        keywords — frozenset de tokens normalizados (minúsculas, sin acentos)
                   para detección O(1).  Ver skills/utils/text.py::normalize().
        patterns — lista de re.Pattern compilados para detección secundaria.
    """

    intent: str
    priority: int = 50  # orden de registro — menor número = mayor prioridad
    keywords: frozenset[str] = frozenset()
    patterns: list[re.Pattern] = []

    def matches(self, text: str) -> bool:
        """Devuelve True si este skill reconoce el texto.

        Primero comprueba keywords (O(1)), luego patterns (O(k·n)).
        Subclases pueden sobreescribir para lógica más compleja.
        """
        norm = normalize(text)
        if _tokenize(norm) & self.keywords:
            return True
        return any(p.search(norm) for p in self.patterns)

    @abstractmethod
    async def handle(self, update, user_id: int, text: str) -> None:
        """Procesa el mensaje y responde al usuario."""
