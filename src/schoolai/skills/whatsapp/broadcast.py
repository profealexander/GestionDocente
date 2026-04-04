"""Comunicado masivo a docentes vía WhatsApp (Green API).

Filtros disponibles:
  - all          → todos los docentes con whatsapp_phone registrado
  - bachillerato → docentes que dictan en 1ro-3ro BT
  - basica       → docentes que dictan en EGB (cualquier subnivel)
  - grade:<id>   → docentes que dictan en un curso específico
  - ids:[1,2,3]  → docentes específicos por ID

Tipos de envío:
  - Texto plano
  - Imagen con caption
  - Documento (PDF, Word, etc.)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.teacher import Teacher, Schedule
from schoolai.skills.whatsapp.sender import send_whatsapp, send_whatsapp_pdf

# Subniveles que pertenecen a básica
_BASICA_SUBLEVELS = {
    "preparatoria", "basica_elemental", "basica_media", "basica_superior",
}
# IDs de grados de bachillerato (13, 14, 15)
_BT_GRADE_IDS = {13, 14, 15}


@dataclass
class BroadcastResult:
    sent: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    no_phone: list[str] = field(default_factory=list)


async def get_broadcast_teachers(
    filter_type: str, session: AsyncSession,
) -> list[Teacher]:
    """Retorna lista de docentes según el filtro indicado."""
    if filter_type == "all":
        teachers = (
            (await session.execute(
                select(Teacher).where(Teacher.is_active == True),  # noqa: E712
            ))
            .unique().scalars().all()
        )
        return [t for t in teachers if t.whatsapp_phone]

    if filter_type in ("bachillerato", "basica"):
        # Docentes que tienen al menos un schedule en el nivel correspondiente
        schedules = (
            (await session.execute(select(Schedule).where(Schedule.is_active == True)))  # noqa: E712
            .unique().scalars().all()
        )
        if filter_type == "bachillerato":
            teacher_ids = {s.teacher_id for s in schedules if s.grade_id in _BT_GRADE_IDS}
        else:
            teacher_ids = {
                s.teacher_id for s in schedules
                if s.grade and s.grade.sublevel in _BASICA_SUBLEVELS
            }
        teachers = (
            (await session.execute(
                select(Teacher).where(
                    Teacher.id.in_(teacher_ids),
                    Teacher.is_active == True,  # noqa: E712
                ),
            ))
            .unique().scalars().all()
        )
        return [t for t in teachers if t.whatsapp_phone]

    if filter_type.startswith("grade:"):
        grade_id = int(filter_type.split(":", 1)[1])
        schedules = (
            (await session.execute(
                select(Schedule).where(
                    Schedule.grade_id == grade_id,
                    Schedule.is_active == True,  # noqa: E712
                ),
            ))
            .unique().scalars().all()
        )
        teacher_ids = {s.teacher_id for s in schedules}
        teachers = (
            (await session.execute(
                select(Teacher).where(Teacher.id.in_(teacher_ids)),
            ))
            .unique().scalars().all()
        )
        return [t for t in teachers if t.whatsapp_phone]

    if filter_type.startswith("ids:"):
        ids = [int(i) for i in filter_type.split(":", 1)[1].split(",")]
        teachers = (
            (await session.execute(
                select(Teacher).where(Teacher.id.in_(ids)),
            ))
            .unique().scalars().all()
        )
        return [t for t in teachers if t.whatsapp_phone]

    return []


async def send_text_broadcast(
    instance_id: str,
    token: str,
    teachers: list[Teacher],
    message: str,
) -> BroadcastResult:
    """Envía mensaje de texto a lista de docentes."""
    result = BroadcastResult()

    async def _send(teacher: Teacher) -> None:
        name = f"{teacher.person.first_name} {teacher.person.last_name}"
        ok = await send_whatsapp(instance_id, token, teacher.whatsapp_phone, message)
        if ok:
            result.sent.append(name)
        else:
            result.failed.append(name)

    await asyncio.gather(*[_send(t) for t in teachers])
    logger.info(f"[broadcast] text sent={len(result.sent)} failed={len(result.failed)}")
    return result


async def send_file_broadcast(
    instance_id: str,
    token: str,
    teachers: list[Teacher],
    file_bytes: bytes,
    file_name: str,
    caption: str = "",
) -> BroadcastResult:
    """Envía archivo (PDF/imagen) a lista de docentes."""
    result = BroadcastResult()

    async def _send(teacher: Teacher) -> None:
        name = f"{teacher.person.first_name} {teacher.person.last_name}"
        ok = await send_whatsapp_pdf(
            instance_id, token, teacher.whatsapp_phone,
            file_bytes, file_name, caption,
        )
        if ok:
            result.sent.append(name)
        else:
            result.failed.append(name)

    await asyncio.gather(*[_send(t) for t in teachers])
    logger.info(f"[broadcast] file sent={len(result.sent)} failed={len(result.failed)}")
    return result
