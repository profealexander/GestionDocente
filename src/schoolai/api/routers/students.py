"""Student endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.api.auth import get_current_user
from schoolai.api.schemas import MessageOut, StudentOut
from schoolai.db.connection import get_session
from schoolai.db.models.person import Person
from schoolai.db.models.student import Student


class StudentCreate(BaseModel):
    first_name: str
    last_name: str
    second_last_name: str = ""
    grade_id: int
    section: str = "A"


class StudentUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    second_last_name: str | None = None
    grade_id: int | None = None
    section: str | None = None
    status: str | None = None


class BulkStudentIn(BaseModel):
    """One name entry for bulk import. full_name = 'APELLIDO1 APELLIDO2, NOMBRE1 NOMBRE2'"""
    full_name: str
    grade_id: int
    section: str = "A"


class BulkImportPayload(BaseModel):
    students: list[BulkStudentIn]

router = APIRouter(
    prefix="/students",
    tags=["Students"],
    dependencies=[Depends(get_current_user)],
)


def _to_out(s: Student) -> StudentOut:
    full_name = s.person.full_name() if s.person else "—"
    return StudentOut(
        id=s.id,
        full_name=full_name,
        grade_id=s.grade_id,
        grade_name=s.grade.name if s.grade else "",
        section=s.section,
        status=s.status,
    )


@router.get(
    "/",
    response_model=list[StudentOut],
    summary="List students",
    description="Returns students optionally filtered by grade or status. Ordered by grade and name.",
)
async def list_students(
    grade_id: Optional[int] = Query(None, description="Filter by grade ID"),
    status: Optional[str] = Query("active", description="Filter by status: active | inactive"),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Student).order_by(Student.grade_id, Student.id)
    if grade_id is not None:
        stmt = stmt.where(Student.grade_id == grade_id)
    if status:
        stmt = stmt.where(Student.status == status)
    result = await session.execute(stmt)
    return [_to_out(s) for s in result.unique().scalars().all()]


@router.get(
    "/{student_id}",
    response_model=StudentOut,
    summary="Get student by ID",
    description="Returns a single student by their ID.",
)
async def get_student(
    student_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Student).where(Student.id == student_id))
    s = result.unique().scalars().first()
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    return _to_out(s)


def _parse_name(full_name: str) -> dict:
    """Parse 'APELLIDO1 APELLIDO2, NOMBRE1 NOMBRE2' or 'NOMBRE APELLIDO'."""
    full_name = full_name.strip()
    if "," in full_name:
        last_part, first_part = full_name.split(",", 1)
        last_names = last_part.strip().split()
        first_names = first_part.strip().split()
        return {
            "last_name": last_names[0] if last_names else "",
            "second_last_name": last_names[1] if len(last_names) > 1 else None,
            "first_name": " ".join(first_names),
        }
    parts = full_name.split()
    if len(parts) >= 2:
        return {"first_name": parts[0], "last_name": parts[-1], "second_last_name": None}
    return {"first_name": full_name, "last_name": "", "second_last_name": None}


async def _create_student(session: AsyncSession, body: StudentCreate) -> Student:
    person = Person(
        first_name=body.first_name.strip().upper(),
        last_name=body.last_name.strip().upper(),
        second_last_name=body.second_last_name.strip().upper() or None,
        role="student",
        status="active",
    )
    session.add(person)
    await session.flush()
    student = Student(person_id=person.id, grade_id=body.grade_id, section=body.section, status="active")
    session.add(student)
    await session.flush()
    await session.refresh(student)
    return student


@router.post("/", response_model=StudentOut, summary="Create student")
async def create_student(
    body: StudentCreate,
    session: AsyncSession = Depends(get_session),
):
    student = await _create_student(session, body)
    await session.commit()
    await session.refresh(student)
    return _to_out(student)


@router.post("/bulk/", response_model=MessageOut, summary="Bulk import students")
async def bulk_import(
    body: BulkImportPayload,
    session: AsyncSession = Depends(get_session),
):
    created = 0
    for entry in body.students:
        parsed = _parse_name(entry.full_name)
        sc = StudentCreate(
            first_name=parsed["first_name"],
            last_name=parsed["last_name"],
            second_last_name=parsed.get("second_last_name") or "",
            grade_id=entry.grade_id,
            section=entry.section,
        )
        await _create_student(session, sc)
        created += 1
    await session.commit()
    return MessageOut(message=f"{created} estudiantes importados correctamente.")


@router.put("/{student_id}", response_model=StudentOut, summary="Update student")
async def update_student(
    student_id: int,
    body: StudentUpdate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Student).where(Student.id == student_id))
    student = result.unique().scalars().first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    person = student.person
    if body.first_name is not None:
        person.first_name = body.first_name.strip().upper()
    if body.last_name is not None:
        person.last_name = body.last_name.strip().upper()
    if body.second_last_name is not None:
        person.second_last_name = body.second_last_name.strip().upper() or None
    if body.grade_id is not None:
        student.grade_id = body.grade_id
    if body.section is not None:
        student.section = body.section
    if body.status is not None:
        student.status = body.status
    await session.commit()
    await session.refresh(student)
    return _to_out(student)
