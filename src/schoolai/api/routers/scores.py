"""Endpoints de notas académicas (gradebook)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.api.auth import get_current_user
from schoolai.db.connection import get_session
from schoolai.db.models.person import Person
from schoolai.db.models.student import Student
from schoolai.db.models.student_score import StudentScore

router = APIRouter(
    prefix="/scores",
    tags=["Scores"],
    dependencies=[Depends(get_current_user)],
)


# ── Schemas ───────────────────────────────────────────────────────────────────


class ScoreRow(BaseModel):
    student_id: int
    subject_id: int
    grade_id: int
    trimester_num: int
    column_label: str
    score: float

    @field_validator("score")
    @classmethod
    def score_range(cls, v: float) -> float:
        if not (0 <= v <= 10):
            raise ValueError("score debe estar entre 0 y 10")
        return round(v, 2)

    @field_validator("column_label")
    @classmethod
    def label_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("column_label no puede estar vacío")
        return v


class StudentScoreOut(BaseModel):
    id: int
    name: str
    scores: dict[str, float | None]


class ScoreMatrixOut(BaseModel):
    grade_id: int
    subject_id: int
    trimester_num: int
    columns: list[str]
    students: list[StudentScoreOut]


class BulkUpsertOut(BaseModel):
    upserted: int


class ColumnDeleteOut(BaseModel):
    deleted: int


# ── Helpers ───────────────────────────────────────────────────────────────────


def _student_name(student: Student) -> str:
    p = student.person
    if not p:
        return f"Estudiante #{student.id}"
    last = (p.last_name or "").title()
    first = (p.first_name or "").title()
    return f"{last} {first}".strip()


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=ScoreMatrixOut, summary="Matriz de notas por curso y materia")
async def get_score_matrix(
    grade_id: int = Query(..., description="ID del curso"),
    subject_id: int = Query(..., description="ID de la materia"),
    trimester: int = Query(1, ge=1, le=3, description="Trimestre (1, 2 o 3)"),
    session: AsyncSession = Depends(get_session),
):
    """Devuelve todos los estudiantes del curso con sus notas por columna.

    Las columnas son las etiquetas únicas registradas para ese curso/materia/trimestre.
    Si un estudiante no tiene nota en una columna, el valor es `null`.
    """
    # 1. Estudiantes activos del curso
    students = (
        await session.execute(
            select(Student)
            .join(Student.person)
            .where(Student.grade_id == grade_id, Student.status == "active")
            .order_by(Person.last_name, Person.first_name),
        )
    ).scalars().all()

    if not students:
        raise HTTPException(status_code=404, detail="No hay estudiantes en este curso")

    student_ids = [s.id for s in students]

    # 2. Notas existentes para este curso / materia / trimestre
    rows = (
        await session.execute(
            select(StudentScore).where(
                StudentScore.grade_id == grade_id,
                StudentScore.subject_id == subject_id,
                StudentScore.trimester_num == trimester,
                StudentScore.student_id.in_(student_ids),
            )
        )
    ).scalars().all()

    # 3. Columnas únicas ordenadas por primera aparición
    columns: list[str] = []
    seen: set[str] = set()
    for r in sorted(rows, key=lambda x: x.created_at):
        if r.column_label not in seen:
            columns.append(r.column_label)
            seen.add(r.column_label)

    # 4. Índice: student_id → {column_label → score}
    score_index: dict[int, dict[str, float]] = {}
    for r in rows:
        score_index.setdefault(r.student_id, {})[r.column_label] = float(r.score)

    student_rows = [
        StudentScoreOut(
            id=s.id,
            name=_student_name(s),
            scores={col: score_index.get(s.id, {}).get(col) for col in columns},
        )
        for s in students
    ]

    return ScoreMatrixOut(
        grade_id=grade_id,
        subject_id=subject_id,
        trimester_num=trimester,
        columns=columns,
        students=student_rows,
    )


@router.put("/bulk", response_model=BulkUpsertOut, summary="Guardar notas (upsert masivo)")
async def bulk_upsert_scores(
    rows: list[ScoreRow],
    session: AsyncSession = Depends(get_session),
):
    """Inserta o actualiza notas. Si ya existe la combinación
    (student_id, subject_id, trimester_num, column_label) la sobreescribe.
    """
    if not rows:
        return BulkUpsertOut(upserted=0)

    values = [
        {
            "student_id": r.student_id,
            "subject_id": r.subject_id,
            "grade_id": r.grade_id,
            "trimester_num": r.trimester_num,
            "column_label": r.column_label,
            "score": r.score,
        }
        for r in rows
    ]

    stmt = (
        insert(StudentScore)
        .values(values)
        .on_conflict_do_update(
            constraint="uq_student_score",
            set_={"score": insert(StudentScore).excluded.score},
        )
    )
    await session.execute(stmt)
    await session.commit()
    return BulkUpsertOut(upserted=len(rows))


@router.delete("/column", response_model=ColumnDeleteOut, summary="Eliminar columna de notas")
async def delete_score_column(
    grade_id: int = Query(...),
    subject_id: int = Query(...),
    trimester: int = Query(..., ge=1, le=3),
    column: str = Query(..., description="Etiqueta de la columna a eliminar"),
    session: AsyncSession = Depends(get_session),
):
    """Elimina todas las notas de una columna específica para un curso/materia/trimestre."""
    result = await session.execute(
        delete(StudentScore).where(
            StudentScore.grade_id == grade_id,
            StudentScore.subject_id == subject_id,
            StudentScore.trimester_num == trimester,
            StudentScore.column_label == column,
        )
    )
    await session.commit()
    return ColumnDeleteOut(deleted=result.rowcount)
