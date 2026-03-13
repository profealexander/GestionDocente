"""initial_homework

Revision ID: d2fe43a33c96
Revises:
Create Date: 2026-03-12 08:09:41.893080

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'd2fe43a33c96'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Database already exists with all tables — no changes needed.
    pass


def downgrade() -> None:
    pass
