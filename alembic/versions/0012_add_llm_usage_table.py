"""add_llm_usage_table

Revision ID: a30d32cf368b
Revises: 0008_attendance_period_time
Create Date: 2026-04-05 11:31:01.805562

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a30d32cf368b'
down_revision: Union[str, Sequence[str], None] = '0008_attendance_period_time'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_usage',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('agent', sa.String(length=40), server_default='unknown', nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('completion_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('cached_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_llm_usage_provider_model', 'llm_usage', ['provider', 'model'], unique=False)
    op.create_index('ix_llm_usage_ts', 'llm_usage', ['ts'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_llm_usage_ts', table_name='llm_usage')
    op.drop_index('ix_llm_usage_provider_model', table_name='llm_usage')
    op.drop_table('llm_usage')
