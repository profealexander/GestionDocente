"""Query the DB and return structured data."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.attendance import Attendance
from schoolai.db.models.grade import Grade
from schoolai.db.models.homework import Homework
from schoolai.db.models.person import Person
from schoolai.db.models.student import Student
from schoolai.skills.query.detector import QueryIntent


@dataclass
class AttendanceEntry:
    date: date
    status: str                    # F | AT | J
    subject_name: str | None = None
    period_start: str | None = None   # "08:00"
    period_end: str | None = None     # "09:30"
    period_number: int | None = None  # school-wide period index (1-based)


@dataclass
class AttendanceRecord:
    student_name: str
    entries: list[AttendanceEntry]


@dataclass
class AttendanceData:
    grade_name: str
    period_start: date
    period_end: date
    period_type: str
    records: list[AttendanceRecord]  # only students with F/AT/J
    total_students: int


@dataclass
class HomeworkRecord:
    id: int
    description: str
    subject: str | None
    delivery_date: date | None
    is_open: bool
    sequence_num: int = 0
    teacher_name: str | None = None


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
    att_stmt = (
        select(Attendance)
        .where(
            and_(
                Attendance.student_id.in_(name_map.keys()),
                Attendance.date >= intent.period_start,
                Attendance.date <= intent.period_end,
                Attendance.status.in_(["F", "AT", "J"]),
            ),
        )
        .order_by(Attendance.student_id, Attendance.date)
    )

    rows = (await session.execute(att_stmt)).scalars().all()

    # For day queries: compute school-wide period numbers from ALL schedules
    # (all days combined to get the correct global bell schedule order)
    start_to_num: dict[str, int] = {}
    if intent.period == "day":
        from schoolai.db.models.teacher import Schedule
        all_starts = [
            row[0]
            for row in (
                await session.execute(
                    select(Schedule.start_time)
                    .where(Schedule.is_active.is_(True))
                    .distinct()
                    .order_by(Schedule.start_time)
                )
            ).all()
        ]
        start_to_num = {s: idx + 1 for idx, s in enumerate(all_starts)}

    # Group by student, preserving subject_name
    by_student: dict[int, list[AttendanceEntry]] = {}
    for row in rows:
        by_student.setdefault(row.student_id, []).append(
            AttendanceEntry(
                date=row.date,
                status=row.status,
                subject_name=row.subject_name,
                period_start=row.period_start,
                period_end=row.period_end,
                period_number=start_to_num.get(row.period_start) if row.period_start else None,
            )
        )

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


async def resolve_attendance_multi(
    intent: QueryIntent,
    grade_ids: list[int],
    session: AsyncSession,
) -> list[AttendanceData]:
    return [await resolve_attendance(intent, gid, session) for gid in grade_ids]


async def resolve_homework_multi(
    intent: QueryIntent,
    grade_ids: list[int],
    session: AsyncSession,
    teacher_subject_ids: list[int] | None = None,
    teacher_id: int | None = None,
) -> list["HomeworkData"]:
    # Sequential — AsyncSession no soporta acceso concurrente desde asyncio.gather
    return [
        await resolve_homework(intent, gid, session, teacher_subject_ids, teacher_id)
        for gid in grade_ids
    ]


async def resolve_homework(
    intent: QueryIntent,
    grade_id: int,
    session: AsyncSession,
    teacher_subject_ids: list[int] | None = None,
    teacher_id: int | None = None,
) -> HomeworkData:
    grade = await session.get(Grade, grade_id)
    grade_name = grade.name if grade else str(grade_id)

    filters = [
        Homework.grade_id == grade_id,
        Homework.submission_date >= intent.period_start,
        Homework.submission_date <= intent.period_end,
    ]
    if intent.trimester_num is not None:
        filters.append(Homework.trimester_num == intent.trimester_num)
    if teacher_subject_ids:
        filters.append(Homework.subject_id.in_(teacher_subject_ids))

    stmt = select(Homework).where(and_(*filters)).order_by(Homework.submission_date.desc())
    rows = (await session.execute(stmt)).scalars().all()

    sf = intent.subject_filter.lower() if intent.subject_filter else None
    records = [
        HomeworkRecord(
            id=hw.id,
            description=hw.homework,
            subject=hw.subject.name if hw.subject else None,
            delivery_date=hw.delivery_date.date() if hw.delivery_date else None,
            is_open=hw.is_open,
            sequence_num=hw.sequence_num,
            teacher_name=(
                f"{hw.teacher.person.first_name} {hw.teacher.person.last_name}".strip()
                if hw.teacher and hw.teacher.person
                else None
            ),
        )
        for hw in rows
        if sf is None or (hw.subject and sf in hw.subject.name.lower())
    ]

    return HomeworkData(
        grade_name=grade_name,
        period_start=intent.period_start,
        period_end=intent.period_end,
        trimester_num=intent.trimester_num,
        records=records,
    )
