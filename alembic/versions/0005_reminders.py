"""recordatorios programados con canal telegram / whatsapp

Revision ID: 0005_reminders
Revises: d9d691ddadf1
Create Date: 2026-03-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_reminders"
down_revision: Union[str, None] = "d9d691ddadf1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("id",           sa.Integer(),                nullable=False),
        sa.Column("teacher_id",   sa.Integer(),                nullable=True),
        sa.Column("grade_id",     sa.Integer(),                nullable=True),
        sa.Column("message",      sa.Text(),                   nullable=False),
        sa.Column("target",       sa.String(20),               nullable=False, server_default="teacher"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True),  nullable=False),
        sa.Column("sent_at",      sa.DateTime(timezone=True),  nullable=True),
        sa.Column("status",       sa.String(20),               nullable=False, server_default="pending"),
        sa.Column("created_at",   sa.DateTime(timezone=True),  nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["grade_id"],   ["grades.id"],   ondelete="SET NULL"),
    )
    op.create_index("ix_reminders_status_scheduled", "reminders", ["status", "scheduled_at"])
    op.create_index("ix_reminders_teacher_id",       "reminders", ["teacher_id"])


def downgrade() -> None:
    op.drop_index("ix_reminders_teacher_id",       table_name="reminders")
    op.drop_index("ix_reminders_status_scheduled", table_name="reminders")
    op.drop_table("reminders")
