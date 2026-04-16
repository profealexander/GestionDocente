"""Búsqueda web via DuckDuckGo — sin API key, sin costo."""

from __future__ import annotations

import asyncio


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Ejecuta una búsqueda DuckDuckGo y retorna resultados.

    Returns:
        Lista de dicts con keys: title, body, url
    """
    from ddgs import DDGS

    def _search() -> list[dict]:
        with DDGS() as ddgs:
            return [
                {"title": r["title"], "body": r["body"], "url": r["href"]}
                for r in ddgs.text(
                    query,
                    max_results=max_results,
                    region="es-ec",      # Ecuador español
                    timelimit="m",       # últimos 30 días
                )
            ]

    return await asyncio.to_thread(_search)
