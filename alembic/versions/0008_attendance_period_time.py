"""attendance: agregar start_time/end_time del período para detalle por hora

Revision ID: 0008_attendance_period_time
Revises: 0007_attendance_subject
Create Date: 2026-03-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_attendance_period_time"
down_revision: Union[str, None] = "0007_attendance_subject"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("attendance", sa.Column("period_start", sa.String(5), nullable=True))
    op.add_column("attendance", sa.Column("period_end", sa.String(5), nullable=True))


def downgrade() -> None:
    op.drop_column("attendance", "period_end")
    op.drop_column("attendance", "period_start")
