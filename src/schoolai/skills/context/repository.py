"""CRUD y full-text search para context_documents."""

from __future__ import annotations

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.context_document import ContextDocument


async def save_document(
    session: AsyncSession,
    teacher_id: int,
    scope: str,
    category: str,
    title: str,
    content: str,
    source_type: str,
    original_filename: str | None = None,
    hint: str | None = None,
) -> ContextDocument:
    doc = ContextDocument(
        teacher_id=teacher_id,
        scope=scope,
        category=category,
        title=title,
        content=content,
        source_type=source_type,
        original_filename=original_filename,
        hint=hint,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def search_documents(
    session: AsyncSession,
    teacher_id: int,
    query: str,
    category: str | None = None,
    limit: int = 3,
) -> list[ContextDocument]:
    """Full-text search en español. Devuelve docs personales del docente + institucionales."""
    base = (
        "SELECT id FROM context_documents "
        "WHERE (teacher_id = :tid OR scope = 'institution') "
        "AND to_tsvector('spanish', coalesce(title,'') || ' ' || coalesce(content,'')) "
        "   @@ plainto_tsquery('spanish', :q) "
    )
    params: dict = {"tid": teacher_id, "q": query, "limit": limit}

    if category:
        base += "AND category = :cat "
        params["cat"] = category

    base += (
        "ORDER BY ts_rank("
        "  to_tsvector('spanish', coalesce(title,'') || ' ' || coalesce(content,'')), "
        "  plainto_tsquery('spanish', :q)"
        ") DESC LIMIT :limit"
    )

    rows = (await session.execute(text(base), params)).fetchall()
    if not rows:
        return []

    ids = [r[0] for r in rows]
    result = await session.execute(
        select(ContextDocument).where(ContextDocument.id.in_(ids)),
    )
    docs = {d.id: d for d in result.scalars().all()}
    return [docs[i] for i in ids if i in docs]


async def list_documents(
    session: AsyncSession,
    teacher_id: int,
    category: str | None = None,
    scope: str | None = None,
    limit: int = 20,
) -> list[ContextDocument]:
    stmt = select(ContextDocument).where(
        or_(
            ContextDocument.teacher_id == teacher_id,
            ContextDocument.scope == "institution",
        ),
    )
    if category:
        stmt = stmt.where(ContextDocument.category == category)
    if scope:
        stmt = stmt.where(ContextDocument.scope == scope)
    stmt = stmt.order_by(ContextDocument.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_document(
    session: AsyncSession,
    doc_id: int,
    teacher_id: int,
) -> bool:
    """Elimina un documento. Solo el docente dueño puede borrar los personales;
    los institucionales los puede borrar cualquier docente (o restringir si se requiere)."""
    doc = await session.get(ContextDocument, doc_id)
    if not doc:
        return False
    if doc.scope == "personal" and doc.teacher_id != teacher_id:
        return False
    await session.delete(doc)
    await session.commit()
    return True
