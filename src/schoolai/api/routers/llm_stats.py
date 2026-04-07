"""LLM usage stats endpoint — agrupado por proveedor y modelo."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.api.auth import get_current_user
from schoolai.db.connection import get_session
from schoolai.db.models.llm_usage import LLMUsage

router = APIRouter(prefix="/llm-stats", tags=["LLM Stats"])


@router.get("", summary="Estadísticas de uso LLM por proveedor y modelo")
async def get_llm_stats(
    since: date | None = Query(None, description="Filtrar desde esta fecha (YYYY-MM-DD)"),
    until: date | None = Query(None, description="Filtrar hasta esta fecha inclusive (YYYY-MM-DD)"),
    session: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
):
    """Retorna tokens consumidos agrupados por proveedor/modelo.

    Acepta filtros opcionales `since` y `until` (YYYY-MM-DD) — sin filtro devuelve
    el histórico completo.  El índice en `ts` asegura que los filtros de fecha sean
    eficientes incluso con millones de registros.

    Cada entrada incluye:
    - **calls**: número de llamadas registradas
    - **prompt_tokens**: tokens de entrada totales
    - **completion_tokens**: tokens de salida totales
    - **cached_tokens**: tokens servidos desde caché (Gemini/OpenAI)
    - **last_used**: timestamp de la última llamada
    """
    stmt = select(
        LLMUsage.provider,
        LLMUsage.model,
        func.count(LLMUsage.id).label("calls"),
        func.sum(LLMUsage.prompt_tokens).label("prompt_tokens"),
        func.sum(LLMUsage.completion_tokens).label("completion_tokens"),
        func.sum(LLMUsage.cached_tokens).label("cached_tokens"),
        func.max(LLMUsage.ts).label("last_used"),
    )
    if since:
        stmt = stmt.where(LLMUsage.ts >= datetime(since.year, since.month, since.day, tzinfo=timezone.utc))
    if until:
        from datetime import timedelta
        next_day = datetime(until.year, until.month, until.day, tzinfo=timezone.utc) + timedelta(days=1)
        stmt = stmt.where(LLMUsage.ts < next_day)
    stmt = stmt.group_by(LLMUsage.provider, LLMUsage.model).order_by(func.count(LLMUsage.id).desc())

    rows = await session.execute(stmt)

    stats = [
        {
            "provider": r.provider,
            "model": r.model,
            "calls": r.calls,
            "prompt_tokens": int(r.prompt_tokens or 0),
            "completion_tokens": int(r.completion_tokens or 0),
            "cached_tokens": int(r.cached_tokens or 0),
            "last_used": r.last_used.isoformat() if r.last_used else None,
        }
        for r in rows
    ]

    total_prompt = sum(s["prompt_tokens"] for s in stats)
    total_completion = sum(s["completion_tokens"] for s in stats)
    total_cached = sum(s["cached_tokens"] for s in stats)
    total_calls = sum(s["calls"] for s in stats)

    return {
        "stats": stats,
        "totals": {
            "calls": total_calls,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "cached_tokens": total_cached,
        },
    }
