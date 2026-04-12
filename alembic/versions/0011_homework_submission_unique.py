"""add unique constraint to homework_submissions

Revision ID: 0011_homework_submission_unique
Revises: 0010_student_scores
Create Date: 2026-04-12

Necesario para el upsert ON CONFLICT DO UPDATE en el endpoint de reporte de cumplimiento.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011_homework_submission_unique"
down_revision: Union[str, None] = "0010_student_scores"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_homework_student",
        "homework_submissions",
        ["homework_id", "student_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_homework_student", "homework_submissions", type_="unique")
