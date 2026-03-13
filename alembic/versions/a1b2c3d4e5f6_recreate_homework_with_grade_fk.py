"""recreate_homework_with_grade_fk

Revision ID: a1b2c3d4e5f6
Revises: 713d9e495915
Create Date: 2026-03-12 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '713d9e495915'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('homework')
    op.create_table(
        'homework',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('homework', sa.Text(), nullable=False),
        sa.Column('grade_id', sa.Integer(), nullable=False),
        sa.Column('subject', sa.String(length=100), nullable=True),
        sa.Column('submission_date', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('delivery_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_open', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.ForeignKeyConstraint(['grade_id'], ['grades.id'], name='homework_grade_id_fkey'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('homework')
    op.create_table(
        'homework',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('homework', sa.Text(), nullable=False),
        sa.Column('course', sa.String(length=100), nullable=False),
        sa.Column('subject', sa.String(length=100), nullable=True),
        sa.Column('submission_date', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('delivery_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_open', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.PrimaryKeyConstraint('id'),
    )
