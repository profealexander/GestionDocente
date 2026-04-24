"""create teacher_absences table

Revision ID: 0009_teacher_absences
Revises: a30d32cf368b
Create Date: 2026-04-06

Tabla dedicada para ausencias del docente durante la jornada.
Separada de attendance (que registra asistencia de estudiantes).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_teacher_absences"
down_revision: Union[str, None] = "a30d32cf368b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teacher_absences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("teachers.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),          # period | day
        sa.Column("period_num", sa.SmallInteger(), nullable=True),
        sa.Column("grade_id", sa.Integer(), sa.ForeignKey("grades.id"), nullable=True),
        sa.Column("subject_name", sa.String(120), nullable=True),
        sa.Column("period_start", sa.String(5), nullable=True),
        sa.Column("period_end", sa.String(5), nullable=True),
        sa.Column("reason", sa.String(20), nullable=False),         # meeting|permit|sick|other
        sa.Column("reason_label", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_teacher_absences_teacher_date", "teacher_absences", ["teacher_id", "date"])
    op.create_index("ix_teacher_absences_date", "teacher_absences", ["date"])


def downgrade() -> None:
    op.drop_index("ix_teacher_absences_date", table_name="teacher_absences")
    op.drop_index("ix_teacher_absences_teacher_date", table_name="teacher_absences")
    op.drop_table("teacher_absences")
