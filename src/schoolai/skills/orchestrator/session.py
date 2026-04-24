"""Ventana de sesión para el orquestador — Redis con fallback en memoria.

Almacena los últimos MAX_PAIRS turnos (usuario + asistente) de una conversación
para que el LLM tenga continuidad dentro de una sesión de trabajo.

Jerarquía de almacenamiento:
  1. Redis (si REDIS_URL está configurado): persiste entre reinicios del bot,
     compartido entre workers, TTL nativo. Recomendado para producción.
  2. Fallback en memoria (_MEMORY_STORE): activo automáticamente cuando Redis
     no está disponible. Funciona en desarrollo sin configuración adicional.
     Se pierde al reiniciar el proceso (watchfiles lo reinicia en file save).

Migración a Redis:
  Agregar REDIS_URL=redis://localhost:6379 al .env y Redis queda activo
  automáticamente — no hay cambios de código necesarios.

Decisiones de diseño:
  - Solo guarda pares user/assistant con texto plano (no tool_call_id).
  - JSON en vez de pickle: más pequeño, debuggable en Redis, sin riesgos.
  - asyncio.to_thread: reutiliza el cliente Redis síncrono sin bloquear el loop.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from loguru import logger

_SESSION_KEY_PREFIX = "agent_sess"
_SESSION_TTL = 1800  # 30 minutos — pausa entre clases = sesión nueva
_MAX_PAIRS = 6  # 6 pares = 12 mensajes — suficiente para continuidad sin inflar el prompt

# ── Fallback en memoria ────────────────────────────────────────────────────────
# Usado automáticamente cuando Redis no está disponible.
# key → (pairs, expires_at) donde expires_at = time.monotonic() + TTL

_MEMORY_STORE: dict[str, tuple[list, float]] = {}


def _memory_get(key: str) -> list | None:
    entry = _MEMORY_STORE.get(key)
    if not entry:
        return None
    pairs, expires_at = entry
    if time.monotonic() > expires_at:
        _MEMORY_STORE.pop(key, None)
        return None
    return pairs


def _memory_set(key: str, val: list, ttl: int) -> None:
    _MEMORY_STORE[key] = (val, time.monotonic() + ttl)


def cleanup_stale_sessions() -> int:
    """Elimina entradas expiradas de _MEMORY_STORE. Llamar desde el job periódico de limpieza."""
    now = time.monotonic()
    expired = [k for k, (_, exp) in _MEMORY_STORE.items() if now > exp]
    for k in expired:
        _MEMORY_STORE.pop(k, None)
    return len(expired)


# ── Redis ──────────────────────────────────────────────────────────────────────


def _get_redis():
    """Retorna el cliente Redis síncrono si está disponible, None si no."""
    try:
        from schoolai.bot.state_store import _redis_client

        return _redis_client
    except ImportError:
        return None


def _redis_get(key: str) -> Any:
    client = _get_redis()
    if client is not None:
        try:
            raw = client.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[session] Redis GET failed, falling back to memory: {exc}")
    return _memory_get(key)


def _redis_set(key: str, val: Any, ttl: int) -> None:
    client = _get_redis()
    if client is not None:
        try:
            client.setex(key, ttl, json.dumps(val, ensure_ascii=False))
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[session] Redis SET failed, falling back to memory: {exc}")
    _memory_set(key, val, ttl)


# ── API pública ────────────────────────────────────────────────────────────────


async def load_session(user_id: int) -> list[dict]:
    """Carga los turnos previos de la sesión como pares user/assistant.

    Returns:
        Lista de dicts {role, content}. Vacía si no hay sesión activa.
        Se inserta DESPUÉS del system prompt y ANTES del mensaje actual.
    """
    key = f"{_SESSION_KEY_PREFIX}:{user_id}"
    pairs: list[dict] | None = await asyncio.to_thread(_redis_get, key)
    if not pairs:
        return []

    messages = []
    for pair in pairs:
        messages.append({"role": "user", "content": pair["user"]})
        messages.append({"role": "assistant", "content": pair["assistant"]})

    logger.debug(f"[session] user={user_id} cargó {len(pairs)} par(es) previos")
    return messages


async def save_session(user_id: int, user_text: str, assistant_reply: str) -> None:
    """Guarda el turno actual y renueva el TTL de la sesión.

    Mantiene los últimos MAX_PAIRS pares. El prefijo anti-injection se elimina
    del texto del usuario antes de guardar para que sea legible como contexto.
    """
    key = f"{_SESSION_KEY_PREFIX}:{user_id}"

    existing: list[dict] = await asyncio.to_thread(_redis_get, key) or []

    # Elimina el prefijo anti-injection si está presente
    clean_text = user_text
    if clean_text.startswith("[Teacher message"):
        clean_text = clean_text.split("\n", 1)[-1].strip()

    existing.append({"user": clean_text, "assistant": assistant_reply})

    if len(existing) > _MAX_PAIRS:
        existing = existing[-_MAX_PAIRS:]

    await asyncio.to_thread(_redis_set, key, existing, _SESSION_TTL)
    logger.debug(f"[session] user={user_id} sesión guardada ({len(existing)} par(es))")
