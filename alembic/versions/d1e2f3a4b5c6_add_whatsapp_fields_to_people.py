"""add phone and callmebot_apikey to people

Revision ID: d1e2f3a4b5c6
Revises: 10993455dc81
Create Date: 2026-03-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = ('b3c4d5e6f7a8', '10993455dc81')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('people', sa.Column('phone', sa.String(), nullable=True))
    op.add_column('people', sa.Column('callmebot_apikey', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('people', 'callmebot_apikey')
    op.drop_column('people', 'phone')
