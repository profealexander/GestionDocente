"""Pydantic schemas for request/response models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Grades ────────────────────────────────────────────────────────────────────

class GradeOut(BaseModel):
    """School grade/course."""
    id: int = Field(description="Unique identifier")
    name: str = Field(description="Grade name (e.g. TERCERO BT, DECIMO EGB)")
    sort_order: int = Field(description="Display order")

    model_config = {"from_attributes": True}


# ── Subjects ──────────────────────────────────────────────────────────────────

class SubjectOut(BaseModel):
    """Academic subject."""
    id: int = Field(description="Unique identifier")
    area: str = Field(description="Knowledge area (e.g. Ciencias Naturales)")
    name: str = Field(description="Subject name (e.g. Física)")
    subnivel: str = Field(description="Education level: basica or bachillerato")

    model_config = {"from_attributes": True}


# ── Homework ──────────────────────────────────────────────────────────────────

class HomeworkOut(BaseModel):
    """Registered homework assignment."""
    id: int = Field(description="Unique identifier")
    homework: str = Field(description="Full homework description as sent by teacher")
    grade_id: int = Field(description="Grade foreign key")
    grade_name: str = Field(description="Grade name")
    subject_id: Optional[int] = Field(None, description="Subject foreign key")
    subject_name: Optional[str] = Field(None, description="Subject name")
    submission_date: datetime = Field(description="Date the homework was registered")
    delivery_date: Optional[datetime] = Field(None, description="Homework due date")
    is_open: bool = Field(description="True if homework is still active")

    model_config = {"from_attributes": True}


class HomeworkClose(BaseModel):
    """Payload to close a homework assignment."""
    is_open: bool = Field(False, description="Set to false to close the homework")


# ── General ───────────────────────────────────────────────────────────────────

class MessageOut(BaseModel):
    """Generic message response."""
    message: str
