"""Esquemas de datos extraídos por el LLM."""
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class AttendanceExtract:
    names: list[str]
    course: str | None
    date: str          # "today" | "yesterday" | "YYYY-MM-DD"
    status: Literal["absent", "late", "justified"]
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
    course: str | None
    period: Literal["today", "yesterday", "week", "last_week", "month", "last_month", "trimester"]
    complete: bool     # False si falta course


@dataclass
class ChatExtract:
    pass


@dataclass
class ExtractionResult:
    intent: Literal["attendance", "homework", "query", "chat"]
    data: AttendanceExtract | HomeworkExtract | QueryExtract | ChatExtract
