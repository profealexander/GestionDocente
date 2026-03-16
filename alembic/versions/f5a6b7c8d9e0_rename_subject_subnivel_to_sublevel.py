"""rename subject subnivel to sublevel

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-03-14

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, Sequence[str], None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('subjects', 'subnivel', new_column_name='sublevel')


def downgrade() -> None:
    op.alter_column('subjects', 'sublevel', new_column_name='subnivel')
