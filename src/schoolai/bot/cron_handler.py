"""Comando /cron — gestiona tareas programadas del bot.

Uso:
    /cron                         — lista todas las tareas con su hora actual
    /cron morning_notify 07:00   — cambia la hora del aviso de jornada

Solo disponible para ADMIN_TELEGRAM_ID.
"""

from __future__ import annotations

import html

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.cron_service import cron_service
from schoolai.config import settings


def _is_admin(user_id: int) -> bool:
    return settings.admin_telegram_id is not None and user_id == settings.admin_telegram_id


async def handle_cron_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not _is_admin(user_id):
        await update.message.reply_text("Solo el administrador puede gestionar tareas programadas.")
        return

    args = context.args or []

    # ── Sin args: listar jobs ──────────────────────────────────────────────────
    if not args:
        jobs = cron_service.list_jobs()
        if not jobs:
            await update.message.reply_text("No hay tareas programadas.")
            return

        lines = ["⏰ <b>Tareas programadas:</b>\n"]
        for j in jobs:
            lines.append(f"• <code>{j['name']}</code>  →  <b>{j['time']}</b>")
            lines.append(f"  {j['description']}\n")
        lines.append("Para cambiar hora: <code>/cron &lt;nombre&gt; HH:MM</code>")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return

    # ── Con args: cambiar hora ─────────────────────────────────────────────────
    if len(args) != 2:
        await update.message.reply_text(
            "Uso: <code>/cron &lt;nombre&gt; HH:MM</code>\n"
            "Ejemplo: <code>/cron morning_notify 07:00</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    job_name, time_str = args
    try:
        hour, minute = (int(p) for p in time_str.split(":"))
    except ValueError:
        await update.message.reply_text(
            "Formato de hora inválido. Usa HH:MM, ej: <code>07:00</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        cron_service.set_time(job_name, hour, minute)
    except ValueError as e:
        await update.message.reply_text(f"Error: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
        return

    await update.message.reply_text(
        f"✅ <b>{job_name}</b> actualizado → <b>{hour:02d}:{minute:02d}</b>\n"
        "El cambio está activo y persiste en reinicios.",
        parse_mode=ParseMode.HTML,
    )
