"""Singleton guard — garantiza que solo una instancia de cada bot corra.

Problema que resuelve:
  watchfiles reinicia el bot enviando SIGTERM a `uv run <bot>`. En WSL2,
  `uv run` puede morir sin propagar la señal al proceso Python hijo, dejando
  un proceso huérfano que sigue llamando a getUpdates. El nuevo proceso también
  llama a getUpdates → Telegram responde con Conflict 409.

Solución:
  Al iniciar, el nuevo proceso lee el PID file de la instancia anterior,
  le envía SIGTERM y espera 1.5s antes de conectar a Telegram. El PID file
  se limpia automáticamente al salir (atexit).

Uso:
    from schoolai.bot.singleton import singleton_guard
    singleton_guard("agente")   # en run_agente()
    singleton_guard("libre")    # en run()
    singleton_guard("jornada")  # en run_dev()
"""

from __future__ import annotations

import atexit
import os
import signal
import time

from loguru import logger

_PID_DIR = "/tmp"


def singleton_guard(bot_name: str) -> None:
    """Mata la instancia anterior del bot y registra el PID actual.

    Args:
        bot_name: identificador único del bot ("agente", "libre", "jornada").
                  Determina el nombre del PID file en /tmp.
    """
    pid_file = f"{_PID_DIR}/schoolai-{bot_name}.pid"
    current_pid = os.getpid()

    # Mata la instancia anterior si el PID file existe
    if os.path.exists(pid_file):
        try:
            with open(pid_file, encoding="utf-8") as f:
                old_pid = int(f.read().strip())

            if old_pid != current_pid:
                # Verificar que siga siendo un proceso schoolai (evita matar PID reutilizados)
                try:
                    with open(f"/proc/{old_pid}/cmdline", "rb") as f:
                        cmdline = f.read().replace(b"\x00", b" ").decode(errors="replace")
                    if "schoolai" not in cmdline:
                        logger.debug(f"[singleton] PID {old_pid} no es schoolai — ignorado")
                        old_pid = None
                except FileNotFoundError:
                    old_pid = None  # proceso ya no existe

                if old_pid:
                    os.kill(old_pid, signal.SIGTERM)
                    logger.info(f"[singleton:{bot_name}] instancia anterior PID={old_pid} terminada")
                    time.sleep(1.5)  # dar tiempo a liberar el socket de Telegram

        except (ValueError, ProcessLookupError, FileNotFoundError):
            pass  # PID file inválido o proceso ya muerto

    # Registra el PID actual
    try:
        with open(pid_file, "w") as f:
            f.write(str(current_pid))
    except OSError as e:
        logger.warning(f"[singleton:{bot_name}] no se pudo escribir PID file: {e}")
        return

    # Limpia el PID file al salir (incluye Ctrl+C y SIGTERM normal)
    def _cleanup():
        try:
            if os.path.exists(pid_file):
                with open(pid_file, encoding="utf-8") as f:
                    if f.read().strip() == str(current_pid):
                        os.unlink(pid_file)
        except OSError:
            pass

    atexit.register(_cleanup)
    logger.debug(f"[singleton:{bot_name}] PID={current_pid} registrado en {pid_file}")
