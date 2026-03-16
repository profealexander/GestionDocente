"""add level and sublevel to grades

Revision ID: e4f5a6b7c8d9
Revises: 10993455dc81
Create Date: 2026-03-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = '10993455dc81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('grades', sa.Column('level',    sa.String(20), nullable=True))
    op.add_column('grades', sa.Column('sublevel', sa.String(20), nullable=True))

    op.execute("UPDATE grades SET level='inicial',      sublevel='inicial_1'        WHERE name='INICIAL 1'")
    op.execute("UPDATE grades SET level='inicial',      sublevel='inicial_2'        WHERE name='INICIAL 2'")
    op.execute("UPDATE grades SET level='egb',          sublevel='preparatoria'     WHERE name='PREPARATORIA'")
    op.execute("UPDATE grades SET level='egb',          sublevel='basica_elemental' WHERE name IN ('SEGUNDO EGB','TERCERO EGB','CUARTO EGB')")
    op.execute("UPDATE grades SET level='egb',          sublevel='basica_media'     WHERE name IN ('QUINTO EGB','SEXTO EGB','SEPTIMO EGB')")
    op.execute("UPDATE grades SET level='egb',          sublevel='basica_superior'  WHERE name IN ('OCTAVO EGB','NOVENO EGB','DECIMO EGB')")
    op.execute("UPDATE grades SET level='bachillerato', sublevel=NULL               WHERE name IN ('PRIMERO BT','SEGUNDO BT','TERCERO BT')")


def downgrade() -> None:
    op.drop_column('grades', 'sublevel')
    op.drop_column('grades', 'level')
