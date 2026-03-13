"""add_area_tecnica_subjects

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-12 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SUBJECTS = [
    ("Área Técnica", "Herramientas Informáticas Empresariales", "bachillerato"),
    ("Área Técnica", "Gestión Contable y Administración Financiera", "bachillerato"),
    ("Área Técnica", "Inglés Técnico Aplicado a los Negocios", "bachillerato"),
]


def upgrade() -> None:
    op.bulk_insert(
        sa.table('subjects',
            sa.column('area', sa.String),
            sa.column('name', sa.String),
            sa.column('subnivel', sa.String),
        ),
        [{"area": a, "name": n, "subnivel": s} for a, n, s in SUBJECTS],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM subjects WHERE area = 'Área Técnica' AND subnivel = 'bachillerato'"
    )
