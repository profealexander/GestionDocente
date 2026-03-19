"""Esquemas de datos para extracción de intención y entidades."""
from dataclasses import dataclass
from typing import Literal


@dataclass
class AttendanceExtract:
    names: list[str]
    course: str | None
    date: str          # "today" | "yesterday" | "YYYY-MM-DD"
    status: Literal["absent", "late", "justified", "all_present"]
    complete: bool     # False si falta course


@dataclass
class HomeworkExtract:
    description: str
    course: str | None
    subject: str | None
    delivery_date: str | None   # "YYYY-MM-DD" | nombre día | None
    complete: bool              # False si falta course o subject


@dataclass
class QueryExtract:
    query_type: Literal["attendance", "homework"]
    courses: list[str]   # abreviaturas de cursos, [] si no se mencionó ninguno
    period: str          # today|yesterday|week|last_week|month|last_month|trimester|...
    complete: bool       # False si courses está vacío
    subject: str | None = None  # materia específica si se mencionó


@dataclass
class HomeworkReportExtract:
    names: list[str]           # quienes no cumplieron
    homework_ref: int | None   # número de tarea (ej: 3)
    course: str | None
    subject: str | None
    status: str                # "missing" | "late" | "partial"
    complete: bool             # False si falta course o homework_ref


@dataclass
class ChatExtract:
    pass


@dataclass
class ExtractionResult:
    intent: Literal["attendance", "homework", "homework_report", "query", "chat"]
    data: AttendanceExtract | HomeworkExtract | HomeworkReportExtract | QueryExtract | ChatExtract
