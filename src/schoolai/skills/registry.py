"""SkillRegistry — registro único de skills y detector de intención.

Patrón first-match: las skills se evalúan en orden de registro.
El orden define la prioridad (más específico primero, ChatSkill al final).

Uso típico:
    from schoolai.skills.registry import registry

    # En main.py/_post_init():
    registry.register(AttendanceSkill())   # 1°
    registry.register(HWReportSkill())     # 2°
    registry.register(HomeworkSkill())     # 3°
    registry.register(QuerySkill())        # 4°
    registry.register(CuotaSkill())        # 5°
    registry.register(ChatSkill())         # 6° — siempre al final

    # Mensaje único → una skill:
    skill = registry.detect(text)
    await skill.handle(update, user_id, text)

    # Mensaje multi-intent → múltiples skills:
    skills = registry.detect_all(text)
    # El Planner divide el texto y asigna fragmentos a cada skill.
"""

from __future__ import annotations

from loguru import logger

from schoolai.skills.base import BaseSkill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: list[BaseSkill] = []
        self._by_intent: dict[str, BaseSkill] = {}
        self._detect_all_cache: dict[str, list[BaseSkill]] = {}

    def register(self, skill: BaseSkill) -> None:
        """Registra una skill. El orden de registro define la prioridad de detección."""
        self._skills.append(skill)
        self._by_intent[skill.intent] = skill
        self._detect_all_cache.clear()
        logger.debug(f"[registry] registered skill: {skill.intent}")

    def detect(self, text: str) -> BaseSkill:
        """Detecta qué skill corresponde al texto.

        Itera las skills en orden de registro y devuelve la primera que hace match.
        Fallback: OrchestratorSkill (si registrada) → ChatSkill.
        """
        for skill in self._skills:
            if skill.matches(text):
                logger.debug(f"[registry] detected intent={skill.intent}")
                return skill
        # Fallback 1: orchestrator (GLM multi-tool)
        orchestrator = self._by_intent.get("orchestrator")
        if orchestrator is not None:
            logger.debug("[registry] no match → orchestrator fallback")
            return orchestrator
        # Fallback 2: chat (si orchestrator no está registrado)
        chat = self._by_intent.get("chat")
        if chat is None:
            raise RuntimeError(
                "ChatSkill no registrada — llama registry.register(ChatSkill()) al arrancar.",
            )
        logger.debug("[registry] no match → chat fallback")
        return chat

    def detect_all(self, text: str) -> list[BaseSkill]:
        """Detecta todas las skills que hacen match con el texto.

        Excluye fallbacks (intent="chat" y intent="orchestrator") — son exclusivos de detect().
        Si ninguna hace match, retorna lista vacía (el caller decide el fallback).
        """
        cached = self._detect_all_cache.get(text)
        if cached is not None:
            return cached
        result = [
            s for s in self._skills
            if s.intent not in ("chat", "orchestrator") and s.matches(text)
        ]
        if len(self._detect_all_cache) >= 256:
            self._detect_all_cache.clear()
        self._detect_all_cache[text] = result
        return result

    def get(self, intent: str) -> BaseSkill | None:
        """Obtiene una skill por su intent. Devuelve None si no existe."""
        return self._by_intent.get(intent)


# Singleton global — importar este objeto en handlers y main.py
registry = SkillRegistry()
