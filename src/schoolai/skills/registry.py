"""SkillRegistry — registro único de skills y detector de intención.

Uso típico:
    from schoolai.skills.registry import registry

    # En main.py al arrancar:
    registry.register(AttendanceSkill())
    registry.register(HomeworkSkill())
    ...

    # En _dispatch():
    skill = registry.detect(text)
    await skill.handle(update, user_id, text)
"""

from __future__ import annotations

from loguru import logger

from schoolai.skills.base import BaseSkill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: list[BaseSkill] = []
        self._by_intent: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """Registra una skill. El orden de registro define la prioridad de detección."""
        self._skills.append(skill)
        self._by_intent[skill.intent] = skill
        logger.debug(f"[registry] registered skill: {skill.intent}")

    def detect(self, text: str) -> BaseSkill:
        """Detecta qué skill corresponde al texto.

        Itera las skills en orden de registro y devuelve la primera que hace match.
        Si ninguna hace match, devuelve la ChatSkill (fallback).
        """
        for skill in self._skills:
            if skill.matches(text):
                logger.debug(f"[registry] detected intent={skill.intent}")
                return skill
        # Fallback a chat (debe ser la última registrada)
        chat = self._by_intent.get("chat")
        if chat is None:
            raise RuntimeError("ChatSkill no registrada — llama registry.register(ChatSkill()) al arrancar.")
        logger.debug("[registry] no match → chat fallback")
        return chat

    def get(self, intent: str) -> BaseSkill | None:
        """Obtiene una skill por su intent. Devuelve None si no existe."""
        return self._by_intent.get(intent)


# Singleton global — importar este objeto en handlers y main.py
registry = SkillRegistry()
