"""Pydantic schemas for request/response models."""

import datetime as dt
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Grades ────────────────────────────────────────────────────────────────────

class GradeOut(BaseModel):
    """School grade/course."""
    id: int = Field(description="Unique identifier")
    name: str = Field(description="Grade name (e.g. TERCERO BT, DECIMO EGB)")
    sort_order: int = Field(description="Display order")
    level: Optional[str] = Field(None, description="Education level: inicial | egb | bachillerato")
    sublevel: Optional[str] = Field(None, description="Sub-level: basica_superior | bachillerato | etc.")

    model_config = {"from_attributes": True}


# ── Subjects ──────────────────────────────────────────────────────────────────

class SubjectOut(BaseModel):
    """Academic subject."""
    id: int = Field(description="Unique identifier")
    area: str = Field(description="Knowledge area (e.g. Ciencias Naturales)")
    name: str = Field(description="Subject name (e.g. Física)")
    sublevel: str = Field(description="Education level: basica or bachillerato")

    model_config = {"from_attributes": True}


# ── Homework ──────────────────────────────────────────────────────────────────

class HomeworkOut(BaseModel):
    """Registered homework assignment."""
    id: int = Field(description="Unique identifier")
    description: str = Field(description="Full homework description")
    grade_id: int = Field(description="Grade foreign key")
    grade_name: str = Field(description="Grade name")
    subject_id: Optional[int] = Field(None, description="Subject foreign key")
    subject_name: Optional[str] = Field(None, description="Subject name")
    sequence_num: int = Field(description="Task number within trimester and grade")
    trimester_num: int = Field(description="Trimester number (1, 2 or 3)")
    submission_date: datetime = Field(description="Date the homework was registered")
    delivery_date: Optional[datetime] = Field(None, description="Homework due date")
    is_open: bool = Field(description="True if homework is still active")

    model_config = {"from_attributes": True}


class HomeworkClose(BaseModel):
    """Payload to close a homework assignment."""
    is_open: bool = Field(False, description="Set to false to close the homework")


# ── Students ──────────────────────────────────────────────────────────────────

class StudentOut(BaseModel):
    """Student record."""
    id: int = Field(description="Unique identifier")
    full_name: str = Field(description="Full name")
    grade_id: int = Field(description="Grade foreign key")
    grade_name: str = Field(description="Grade name")
    section: str = Field(description="Section within the grade")
    status: str = Field(description="Student status: active | inactive")

    model_config = {"from_attributes": True}


# ── Attendance ────────────────────────────────────────────────────────────────

class AttendanceOut(BaseModel):
    """Attendance record."""
    id: int = Field(description="Unique identifier")
    student_id: Optional[int] = Field(None, description="Student foreign key")
    student_name: Optional[str] = Field(None, description="Student full name")
    grade_id: Optional[int] = Field(None, description="Grade ID (from student)")
    date: dt.date = Field(description="Attendance date")
    status: str = Field(description="F = absent | AT = late | J = justified")
    notes: Optional[str] = Field(None, description="Optional notes")

    model_config = {"from_attributes": True}


# ── General ───────────────────────────────────────────────────────────────────

class MessageOut(BaseModel):
    """Generic message response."""
    message: str
