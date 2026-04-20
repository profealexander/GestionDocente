"""Inicialización común a todos los bots de SchoolAI.

Contiene la lógica que se repite en cada _post_init:
  - init_redis
  - load_course_map (carga inicial)
  - job periódico de cleanup de StateStores + sesiones LLM + recarga de cursos
  - job periódico del dispatcher de recordatorios (opcional)

Uso en _post_init de cada bot:
    from schoolai.bot.startup import common_post_init
    await common_post_init(app, register_reminders=True, log_label="agente")
"""

from __future__ import annotations

from loguru import logger


async def common_post_init(
    app,
    *,
    register_reminders: bool = False,
    log_label: str = "bot",
) -> None:
    """Inicialización compartida por todos los bots.

    Args:
        app:                Instancia de Application de python-telegram-bot.
        register_reminders: Si True, registra el job periódico del dispatcher.
        log_label:          Prefijo para los mensajes de log (ej: "bot", "agente").
    """
    from schoolai.bot.state import init_redis
    from schoolai.config import settings
    from schoolai.skills.utils.courses import load_course_map

    if not settings.redis_url:
        logger.debug(
            "[startup] REDIS_URL no configurado — estado de sesión en RAM (sin persistencia entre reinicios).",
        )
    init_redis(settings.redis_url)
    await load_course_map()

    if register_reminders:
        from schoolai.skills.autonomy.jobs import register_jobs
        await register_jobs(app.bot)

    async def _cleanup_job(ctx) -> None:
        from schoolai.bot.state import cleanup_stale, clear_jornada_all_stale
        from schoolai.skills.orchestrator.session import cleanup_stale_sessions
        from schoolai.skills.utils.courses import load_course_map as _reload

        removed = cleanup_stale()
        removed += clear_jornada_all_stale()
        removed += cleanup_stale_sessions()
        if removed:
            logger.debug(f"[{log_label}:cleanup] {removed} estados expirados eliminados")
        await _reload()  # no-op si el mapa tiene menos de 1 h

    app.job_queue.run_repeating(_cleanup_job, interval=600, first=600)
