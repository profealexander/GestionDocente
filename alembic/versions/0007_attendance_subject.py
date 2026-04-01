"""attendance: agregar subject_name para seguimiento por materia

Revision ID: 0007_attendance_subject
Revises: 0006_context_documents
Create Date: 2026-03-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_attendance_subject"
down_revision: Union[str, None] = "0006_context_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attendance",
        sa.Column("subject_name", sa.String(120), nullable=True),
    )
    # Índice para acelerar consultas de asistencia por alumno+fecha+materia
    op.create_index(
        "ix_attendance_student_date_subject",
        "attendance",
        ["student_id", "date", "subject_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_attendance_student_date_subject", table_name="attendance")
    op.drop_column("attendance", "subject_name")
