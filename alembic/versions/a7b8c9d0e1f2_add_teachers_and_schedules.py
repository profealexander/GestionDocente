"""add teachers and schedules

Revision ID: a7b8c9d0e1f2
Revises: f5a6b7c8d9e0
Create Date: 2026-03-15

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'teachers',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('person_id', sa.Integer, sa.ForeignKey('people.id'), nullable=False, unique=True),
        sa.Column('telegram_id', sa.BigInteger, nullable=True, unique=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='1'),
    )

    op.create_table(
        'schedules',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('teacher_id', sa.Integer, sa.ForeignKey('teachers.id'), nullable=False),
        sa.Column('day_of_week', sa.SmallInteger, nullable=False),
        sa.Column('period_num', sa.SmallInteger, nullable=False),
        sa.Column('start_time', sa.String(5), nullable=False),
        sa.Column('end_time', sa.String(5), nullable=False),
        sa.Column('grade_id', sa.Integer, sa.ForeignKey('grades.id'), nullable=False),
        sa.Column('subject_id', sa.Integer, sa.ForeignKey('subjects.id'), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='1'),
    )


def downgrade() -> None:
    op.drop_table('schedules')
    op.drop_table('teachers')
