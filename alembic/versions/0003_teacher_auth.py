"""teacher username + password_hash columns

Revision ID: 0003_teacher_auth
Revises: 0002_notifications
Create Date: 2026-03-17
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0003_teacher_auth"
down_revision: Union[str, None] = "0002_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("teachers", sa.Column("username", sa.String(64), nullable=True))
    op.add_column("teachers", sa.Column("password_hash", sa.String(128), nullable=True))
    op.create_unique_constraint("uq_teachers_username", "teachers", ["username"])


def downgrade() -> None:
    op.drop_constraint("uq_teachers_username", "teachers", type_="unique")
    op.drop_column("teachers", "password_hash")
    op.drop_column("teachers", "username")
