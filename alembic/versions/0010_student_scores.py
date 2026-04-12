"""create student_scores table

Revision ID: 0010_student_scores
Revises: 0009_teacher_absences
Create Date: 2026-04-11

Tabla de notas académicas: una fila por (estudiante, materia, trimestre, columna).
Las columnas son etiquetas libres definidas por el docente ("P1", "Lección 1", etc.).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_student_scores"
down_revision: Union[str, None] = "0009_teacher_absences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.Integer(),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "grade_id",
            sa.Integer(),
            sa.ForeignKey("grades.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "teacher_id",
            sa.Integer(),
            sa.ForeignKey("teachers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trimester_num", sa.Integer(), nullable=False),
        sa.Column("column_label", sa.String(50), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "student_id", "subject_id", "trimester_num", "column_label",
            name="uq_student_score",
        ),
    )
    op.create_index(
        "ix_student_scores_lookup",
        "student_scores",
        ["grade_id", "subject_id", "trimester_num"],
    )


def downgrade() -> None:
    op.drop_index("ix_student_scores_lookup", table_name="student_scores")
    op.drop_table("student_scores")
