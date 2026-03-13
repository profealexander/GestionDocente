"""Query the DB and return structured data."""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.attendance import Attendance
from schoolai.db.models.grade import Grade
from schoolai.db.models.homework import Homework
from schoolai.db.models.person import Person
from schoolai.db.models.student import Student
from schoolai.skills.query.detector import QueryIntent


@dataclass
class AttendanceRecord:
    student_name: str
    entries: list[tuple[date, str]]  # [(date, status)]


@dataclass
class AttendanceData:
    grade_name: str
    period_start: date
    period_end: date
    period_type: str
    records: list[AttendanceRecord]   # only students with F/AT/J
    total_students: int


@dataclass
class HomeworkRecord:
    id: int
    description: str
    subject: str | None
    delivery_date: date | None
    is_open: bool


@dataclass
class HomeworkData:
    grade_name: str
    period_start: date
    period_end: date
    trimester_num: int | None
    records: list[HomeworkRecord]


async def resolve_attendance(
    intent: QueryIntent,
    grade_id: int,
    session: AsyncSession,
) -> AttendanceData:
    grade = await session.get(Grade, grade_id)
    grade_name = grade.name if grade else str(grade_id)

    # All active students for grade
    stmt = (
        select(Student)
        .where(Student.grade_id == grade_id, Student.status == "active")
        .order_by(Student.id)
    )
    students = (await session.execute(stmt)).unique().scalars().all()
    total = len(students)

    # Build student_id → name map
    name_map: dict[int, str] = {}
    for s in students:
        if s.person:
            p: Person = s.person
            name_map[s.id] = f"{p.first_name} {p.last_name}".strip()

    # Fetch attendance records in period
    att_stmt = select(Attendance).where(
        and_(
            Attendance.student_id.in_(name_map.keys()),
            Attendance.date >= intent.period_start,
            Attendance.date <= intent.period_end,
            Attendance.status.in_(["F", "AT", "J"]),
        )
    ).order_by(Attendance.student_id, Attendance.date)

    rows = (await session.execute(att_stmt)).scalars().all()

    # Group by student
    by_student: dict[int, list[tuple[date, str]]] = {}
    for row in rows:
        by_student.setdefault(row.student_id, []).append((row.date, row.status))

    records = [
        AttendanceRecord(student_name=name_map[sid], entries=entries)
        for sid, entries in sorted(by_student.items(), key=lambda x: name_map.get(x[0], ""))
    ]

    return AttendanceData(
        grade_name=grade_name,
        period_start=intent.period_start,
        period_end=intent.period_end,
        period_type=intent.period,
        records=records,
        total_students=total,
    )


async def resolve_homework(
    intent: QueryIntent,
    grade_id: int,
    session: AsyncSession,
) -> HomeworkData:
    grade = await session.get(Grade, grade_id)
    grade_name = grade.name if grade else str(grade_id)

    stmt = (
        select(Homework)
        .where(
            and_(
                Homework.grade_id == grade_id,
                Homework.submission_date >= intent.period_start,
                Homework.submission_date <= intent.period_end,
            )
        )
        .order_by(Homework.submission_date.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()

    records = [
        HomeworkRecord(
            id=hw.id,
            description=hw.homework,
            subject=hw.subject.name if hw.subject else None,
            delivery_date=hw.delivery_date.date() if hw.delivery_date else None,
            is_open=hw.is_open,
        )
        for hw in rows
    ]

    return HomeworkData(
        grade_name=grade_name,
        period_start=intent.period_start,
        period_end=intent.period_end,
        trimester_num=intent.trimester_num,
        records=records,
    )
