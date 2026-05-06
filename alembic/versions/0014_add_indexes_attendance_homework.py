"""add_indexes_attendance_homework

Revision ID: d9d691ddadf1
Revises: a31faf8efe5a
Create Date: 2026-03-27

Adds performance indexes on hot query paths:
  - attendance(student_id, date)      — edit-attendance join + idempotent save_absences
  - attendance(date)                  — per-grade daily listing
  - homework(grade_id, trimester_num) — list_open, dedup check, consultar_tareas
  - homework(subject_id)              — per-subject task queries
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d9d691ddadf1"
down_revision: Union[str, Sequence[str], None] = "a31faf8efe5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_attendance_student_date", "attendance", ["student_id", "date"])
    op.create_index("ix_attendance_date", "attendance", ["date"])
    op.create_index("ix_homework_grade_trimester", "homework", ["grade_id", "trimester_num"])
    op.create_index("ix_homework_subject", "homework", ["subject_id"])


def downgrade() -> None:
    op.drop_index("ix_homework_subject", table_name="homework")
    op.drop_index("ix_homework_grade_trimester", table_name="homework")
    op.drop_index("ix_attendance_date", table_name="attendance")
    op.drop_index("ix_attendance_student_date", table_name="attendance")
