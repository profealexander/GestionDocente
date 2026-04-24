"""notifications table

Revision ID: 0002_notifications
Revises: 0001_baseline
Create Date: 2026-03-16
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = '0002_notifications'
down_revision: Union[str, Sequence[str], None] = '0001_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id',          sa.Integer,                 primary_key=True, autoincrement=True),
        sa.Column('teacher_id',  sa.Integer,                 sa.ForeignKey('teachers.id',  ondelete='SET NULL'), nullable=True),
        sa.Column('student_id',  sa.Integer,                 sa.ForeignKey('students.id',  ondelete='SET NULL'), nullable=True),
        sa.Column('subject_id',  sa.Integer,                 sa.ForeignKey('subjects.id',  ondelete='SET NULL'), nullable=True),
        sa.Column('homework_id', sa.Integer,                 sa.ForeignKey('homework.id',  ondelete='SET NULL'), nullable=True),
        sa.Column('type',        sa.String(30),              nullable=False, server_default='tarea'),
        sa.Column('anio',        sa.SmallInteger,            nullable=False),
        sa.Column('teacher_seq', sa.Integer,                 nullable=False),
        sa.Column('student_seq', sa.Integer,                 nullable=False),
        sa.Column('num_doc',     sa.String(50),              nullable=False, unique=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('notifications')
