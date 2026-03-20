"""Endpoints REST para cuotas y actividades escolares."""

import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.api.auth import get_current_user
from schoolai.db.connection import get_session
from schoolai.skills.cuotas.service import (
    add_participantes,
    create_actividad,
    get_actividad_by_nombre,
    get_actividades,
    get_estado_actividad,
    get_students_in_grade,
    register_pago,
)

router = APIRouter(
    prefix="/actividades",
    tags=["Cuotas"],
    dependencies=[Depends(get_current_user)],
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ActividadCreate(BaseModel):
    nombre: str
    monto: float
    descripcion: Optional[str] = None

    @field_validator("monto")
    @classmethod
    def monto_positivo(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("El monto debe ser positivo")
        return v


class ActividadOut(BaseModel):
    id: int
    nombre: str
    monto: float
    descripcion: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PagoOut(BaseModel):
    id: int
    monto: float
    paid_at: datetime
    notas: Optional[str]

    model_config = {"from_attributes": True}


class ParticipanteOut(BaseModel):
    id: int
    student_id: int
    student_name: str       # apellidos + nombres
    total_pagado: float
    is_complete: bool
    pagos: list[PagoOut]

    model_config = {"from_attributes": True}


class ActividadDetalle(ActividadOut):
    total_recaudado: float
    total_completos: int
    total_pendientes: int
    participantes: list[ParticipanteOut]


class AddParticipantesBody(BaseModel):
    grade_id: int


class PagoCreate(BaseModel):
    student_id: int
    monto: float
    notas: Optional[str] = None

    @field_validator("monto")
    @classmethod
    def monto_positivo(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("El monto debe ser positivo")
        return v


class PagoOut2(BaseModel):
    pago_id: int
    student_id: int
    total_pagado: float
    is_complete: bool
    monto_registrado: float


# ── Helpers ───────────────────────────────────────────────────────────────────

def _student_display(student) -> str:
    last  = getattr(student, "last_name",  "") or ""
    first = getattr(student, "first_name", "") or ""
    return f"{last.title()} {first.title()}".strip()


def _to_participante(p) -> ParticipanteOut:
    return ParticipanteOut(
        id=p.id,
        student_id=p.student_id,
        student_name=_student_display(p.student) if p.student else "",
        total_pagado=float(p.total_pagado or 0),
        is_complete=p.is_complete,
        pagos=[
            PagoOut(
                id=pg.id,
                monto=float(pg.monto),
                paid_at=pg.paid_at,
                notas=pg.notas,
            )
            for pg in (p.pagos or [])
        ],
    )


def _to_detalle(actividad, participantes) -> ActividadDetalle:
    recaudado  = sum(float(p.total_pagado or 0) for p in participantes)
    completos  = sum(1 for p in participantes if p.is_complete)
    pendientes = len(participantes) - completos
    return ActividadDetalle(
        id=actividad.id,
        nombre=actividad.nombre,
        monto=float(actividad.monto),
        descripcion=actividad.descripcion,
        is_active=actividad.is_active,
        created_at=actividad.created_at,
        total_recaudado=recaudado,
        total_completos=completos,
        total_pendientes=pendientes,
        participantes=[_to_participante(p) for p in participantes],
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=list[ActividadOut],
    summary="Listar actividades",
)
async def list_actividades(
    only_active: bool = True,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    teacher_id = getattr(current_user, "teacher_id", None) or getattr(current_user, "id", None)
    actividades = await get_actividades(session, teacher_id=teacher_id, only_active=only_active)
    return [
        ActividadOut(
            id=a.id, nombre=a.nombre, monto=float(a.monto),
            descripcion=a.descripcion, is_active=a.is_active, created_at=a.created_at,
        )
        for a in actividades
    ]


@router.post(
    "/",
    response_model=ActividadOut,
    status_code=201,
    summary="Crear actividad",
)
async def create_actividad_endpoint(
    body: ActividadCreate,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    teacher_id = getattr(current_user, "teacher_id", None) or getattr(current_user, "id", None)
    actividad = await create_actividad(
        session,
        nombre=body.nombre,
        monto=body.monto,
        teacher_id=teacher_id,
        descripcion=body.descripcion,
    )
    return ActividadOut(
        id=actividad.id, nombre=actividad.nombre, monto=float(actividad.monto),
        descripcion=actividad.descripcion, is_active=actividad.is_active,
        created_at=actividad.created_at,
    )


@router.get(
    "/{actividad_id}/",
    response_model=ActividadDetalle,
    summary="Detalle de actividad con participantes",
)
async def get_actividad(
    actividad_id: int,
    session: AsyncSession = Depends(get_session),
):
    actividad, participantes = await get_estado_actividad(session, actividad_id)
    if not actividad:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    return _to_detalle(actividad, participantes)


@router.post(
    "/{actividad_id}/participantes/",
    summary="Agregar estudiantes de un curso como participantes",
    response_model=dict,
)
async def add_grade_participantes(
    actividad_id: int,
    body: AddParticipantesBody,
    session: AsyncSession = Depends(get_session),
):
    actividad = await session.get(__import__("schoolai.db.models.cuota", fromlist=["Actividad"]).Actividad, actividad_id)
    if not actividad:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")

    students = await get_students_in_grade(session, body.grade_id)
    if not students:
        raise HTTPException(status_code=404, detail="No hay estudiantes en ese curso")

    added = await add_participantes(session, actividad_id, [s.id for s in students])
    return {"added": added, "total_in_grade": len(students)}


@router.post(
    "/{actividad_id}/pagos/",
    response_model=PagoOut2,
    status_code=201,
    summary="Registrar pago de un estudiante",
)
async def create_pago(
    actividad_id: int,
    body: PagoCreate,
    session: AsyncSession = Depends(get_session),
):
    from schoolai.db.models.cuota import Actividad
    actividad = await session.get(Actividad, actividad_id)
    if not actividad:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")

    pago, participante = await register_pago(
        session,
        actividad_id=actividad_id,
        student_id=body.student_id,
        monto=body.monto,
        notas=body.notas,
    )
    return PagoOut2(
        pago_id=pago.id,
        student_id=participante.student_id,
        total_pagado=float(participante.total_pagado),
        is_complete=participante.is_complete,
        monto_registrado=body.monto,
    )


@router.get(
    "/{actividad_id}/export/",
    summary="Exportar reporte Excel de la actividad",
    response_class=Response,
    responses={
        200: {
            "content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}},
            "description": "Archivo Excel con el estado de pagos",
        }
    },
)
async def export_actividad(
    actividad_id: int,
    session: AsyncSession = Depends(get_session),
):
    from schoolai.skills.cuotas.exporter import export_actividad_excel

    actividad, participantes = await get_estado_actividad(session, actividad_id)
    if not actividad:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    if not participantes:
        raise HTTPException(status_code=422, detail="La actividad no tiene participantes aún")

    xlsx_bytes = export_actividad_excel(actividad, participantes)
    filename = f"cuotas_{actividad.nombre.lower().replace(' ', '_')}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
