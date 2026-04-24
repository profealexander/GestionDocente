"""Backward-compat shim — el código vive en bot/jornada/.

Este módulo re-exporta los símbolos públicos para no romper importaciones
existentes en main.py, main_agente.py y handlers.py.
"""

from schoolai.bot.jornada import (  # noqa: F401
    _finish_jornada,
    _horario_interceptor,
    _send_period_card,
    handle_horario_callback,
    handle_horario_command,
    handle_jornada_callback,
    handle_jornada_command,
    job_morning_notify,
    job_reconnect_resume,
    jornada_context_banner,
)
