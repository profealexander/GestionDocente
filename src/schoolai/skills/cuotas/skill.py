"""CuotaSkill — detecta y procesa mensajes relacionados con cuotas de actividades."""

from __future__ import annotations

import re

from schoolai.skills.base import BaseSkill
from schoolai.skills.utils.text import normalize


class CuotaSkill(BaseSkill):
    """Maneja: crear actividad, registrar pago, ver estado, exportar reporte."""

    intent = "cuota"

    keywords: frozenset[str] = frozenset(normalize(w) for w in (
        "cuota", "cuotas", "actividad", "actividades",
        "pago", "pagos", "pago cuota",
        "nueva actividad", "crear actividad",
    ))

    patterns: list[re.Pattern] = [
        re.compile(
            r"\b(nueva?\s+actividad|crear\s+actividad|agregar\s+actividad"
            r"|nueva\s+cuota|crear\s+cuota"
            r"|pag[oó]\s+\$?\d"          # "García pagó $30"
            r"|abono\s+\$?\d"
            r"|ver\s+cuotas?|estado\s+cuotas?"
            r"|cuotas?\s+de\s+\w"
            r"|reporte\s+cuotas?"
            r"|listar\s+actividades?"
            r"|ver\s+actividades?"
            r"|actividades?\s+activas?"
            r"|falta\s+pagar"
            r"|pendiente[s]?\s+cuotas?"
            r"|quién\s+(no\s+)?pag[oó]"
            r"|quien\s+(no\s+)?pago"
            r"|exportar\s+cuotas?"
            r")\b",
            re.IGNORECASE,
        )
    ]

    async def handle(self, update, user_id: int, text: str) -> None:
        from schoolai.skills.cuotas.extractor import extract_cuota
        from schoolai.skills.cuotas.handler import (
            handle_create,
            handle_export,
            handle_list,
            handle_pago,
            handle_query,
        )

        data = extract_cuota(text)
        if data is None:
            await update.message.reply_text(
                "No entendí la instrucción de cuotas.\n"
                "Ejemplos:\n"
                "• _nueva actividad \"Paseo\" $50_\n"
                "• _García pagó $30 para el Paseo_\n"
                "• _ver cuotas Paseo_\n"
                "• _listar actividades_",
                parse_mode="Markdown",
            )
            return

        if data.action == "create":
            await handle_create(update, user_id, data)
        elif data.action == "list":
            await handle_list(update, user_id)
        elif data.action == "query":
            await handle_query(update, user_id, data)
        elif data.action == "pago":
            await handle_pago(update, user_id, data)
        elif data.action == "export":
            await handle_export(update, user_id, data)
        else:
            await update.message.reply_text("Acción no reconocida.")
