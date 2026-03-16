"""add_teacher_id_to_homework

Revision ID: eba880c520bd
Revises: f3a4b5c6d7e8
Create Date: 2026-03-16

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = 'eba880c520bd'
down_revision: Union[str, Sequence[str], None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('homework', sa.Column('teacher_id', sa.Integer(), sa.ForeignKey('teachers.id', ondelete='SET NULL'), nullable=True))


def downgrade() -> None:
    op.drop_column('homework', 'teacher_id')
