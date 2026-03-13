"""add_subject_to_homework

Revision ID: 713d9e495915
Revises: d2fe43a33c96
Create Date: 2026-03-12 09:51:28.073832

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '713d9e495915'
down_revision: Union[str, Sequence[str], None] = 'd2fe43a33c96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('homework', sa.Column('subject', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('homework', 'subject')
