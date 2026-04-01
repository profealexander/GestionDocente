"""Funciones LLM tools para gestión de documentos de contexto."""

from __future__ import annotations


async def search_context(
    telegram_id: int,
    query: str,
    category: str | None = None,
) -> str:
    """Busca en los documentos de contexto del docente (personales + institucionales)."""
    from sqlalchemy import select

    from schoolai.db.connection import async_session
    from schoolai.db.models.teacher import Teacher
    from schoolai.skills.context.repository import search_documents

    async with async_session() as session:
        teacher = (
            await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if not teacher:
            return "No se encontró tu perfil de docente."

        docs = await search_documents(session, teacher.id, query, category=category)

    if not docs:
        return "No se encontraron documentos relevantes para esa consulta."

    parts = []
    for doc in docs:
        scope_label = "Institucional" if doc.scope == "institution" else "Personal"
        parts.append(
            f"[{doc.title}] ({scope_label} — {doc.category})\n{doc.content[:800]}"
        )
    return "\n\n---\n\n".join(parts)


async def list_context_docs(
    telegram_id: int,
    category: str | None = None,
    scope: str | None = None,
) -> str:
    """Lista los documentos de contexto disponibles para el docente."""
    from sqlalchemy import select

    from schoolai.db.connection import async_session
    from schoolai.db.models.teacher import Teacher
    from schoolai.skills.context.repository import list_documents

    async with async_session() as session:
        teacher = (
            await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if not teacher:
            return "No se encontró tu perfil de docente."

        docs = await list_documents(session, teacher.id, category=category, scope=scope)

    if not docs:
        return "No hay documentos de contexto cargados."

    lines = ["Documentos disponibles:"]
    for doc in docs:
        scope_icon = "🏫" if doc.scope == "institution" else "👤"
        lines.append(
            f"  {scope_icon} #{doc.id} [{doc.category}] {doc.title}"
        )
    return "\n".join(lines)


async def delete_context_doc(telegram_id: int, doc_id: int) -> str:
    """Elimina un documento de contexto por ID."""
    from sqlalchemy import select

    from schoolai.db.connection import async_session
    from schoolai.db.models.teacher import Teacher
    from schoolai.skills.context.repository import delete_document

    async with async_session() as session:
        teacher = (
            await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if not teacher:
            return "No se encontró tu perfil de docente."

        ok = await delete_document(session, doc_id, teacher.id)

    if ok:
        return f"Documento #{doc_id} eliminado."
    return f"No se pudo eliminar el documento #{doc_id}. Verifica que exista y sea tuyo."
