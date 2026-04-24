"""Tools de documentos de contexto y búsqueda web."""

from __future__ import annotations

from schoolai.skills.context.tools import (
    delete_context_doc,
    list_context_docs,
    save_web_page,
    search_context,
    web_search,
)


async def _search_context(
    telegram_id: int,
    query: str,
    category: str | None = None,
) -> str:
    """Searches the teacher's context documents (personal and institutional)."""
    return await search_context(telegram_id=telegram_id, query=query, category=category)


async def _list_context_docs(
    telegram_id: int,
    category: str | None = None,
    scope: str | None = None,
) -> str:
    """Lists available context documents for the teacher."""
    return await list_context_docs(telegram_id=telegram_id, category=category, scope=scope)


async def _delete_context_doc(telegram_id: int, doc_id: int) -> str:
    """Deletes a context document by ID."""
    return await delete_context_doc(telegram_id=telegram_id, doc_id=doc_id)


async def _web_search(query: str) -> str:
    """Searches the internet via DuckDuckGo and returns top results."""
    return await web_search(query=query)


async def _save_web_page(telegram_id: int, url: str, hint: str | None = None) -> str:
    """Downloads a web page and saves it as a context document."""
    return await save_web_page(telegram_id=telegram_id, url=url, hint=hint)
