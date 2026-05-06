"""teacher_whatsapp_phone

Revision ID: a31faf8efe5a
Revises: 0004_cuotas
Create Date: 2026-03-21

Agrega columna whatsapp_phone a teachers para identificar docentes
que envían mensajes desde WhatsApp (canal bidireccional via Green API).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a31faf8efe5a"
down_revision: Union[str, Sequence[str], None] = "0004_cuotas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("teachers", sa.Column("whatsapp_phone", sa.String(length=20), nullable=True))
    op.create_unique_constraint("uq_teachers_whatsapp_phone", "teachers", ["whatsapp_phone"])


def downgrade() -> None:
    op.drop_constraint("uq_teachers_whatsapp_phone", "teachers", type_="unique")
    op.drop_column("teachers", "whatsapp_phone")
