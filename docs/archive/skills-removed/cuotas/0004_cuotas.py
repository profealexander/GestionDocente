"""control de cuotas: actividades, participantes, pagos con evidencia

Revision ID: 0004_cuotas
Revises: 0003_teacher_auth
Create Date: 2026-03-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_cuotas"
down_revision: Union[str, None] = "0003_teacher_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "actividades",
        sa.Column("id",          sa.Integer(),                          nullable=False),
        sa.Column("teacher_id",  sa.Integer(),                          nullable=True),
        sa.Column("nombre",      sa.String(120),                        nullable=False),
        sa.Column("descripcion", sa.Text(),                             nullable=True),
        sa.Column("monto",       sa.Numeric(precision=10, scale=2),     nullable=False),
        sa.Column("is_active",   sa.Boolean(),                          nullable=False, server_default=sa.text("true")),
        sa.Column("created_at",  sa.DateTime(timezone=True),            nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "actividad_participantes",
        sa.Column("id",           sa.Integer(),                       nullable=False),
        sa.Column("actividad_id", sa.Integer(),                       nullable=False),
        sa.Column("student_id",   sa.Integer(),                       nullable=False),
        sa.Column("total_pagado", sa.Numeric(precision=10, scale=2),  nullable=False, server_default=sa.text("0")),
        sa.Column("is_complete",  sa.Boolean(),                       nullable=False, server_default=sa.text("false")),
        sa.Column("created_at",   sa.DateTime(timezone=True),         nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["actividad_id"], ["actividades.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"],   ["students.id"],    ondelete="CASCADE"),
        sa.UniqueConstraint("actividad_id", "student_id", name="uq_actividad_student"),
    )
    op.create_index("ix_actividad_participantes_actividad_id", "actividad_participantes", ["actividad_id"])
    op.create_index("ix_actividad_participantes_student_id",   "actividad_participantes", ["student_id"])

    op.create_table(
        "actividad_pagos",
        sa.Column("id",               sa.Integer(),                      nullable=False),
        sa.Column("participante_id",  sa.Integer(),                      nullable=False),
        sa.Column("monto",            sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("paid_at",          sa.DateTime(timezone=True),        nullable=False, server_default=sa.func.now()),
        sa.Column("notas",            sa.Text(),                         nullable=True),
        sa.Column("telegram_file_id", sa.String(256),                    nullable=True),
        sa.Column("file_type",        sa.String(16),                     nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["participante_id"], ["actividad_participantes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_actividad_pagos_participante_id", "actividad_pagos", ["participante_id"])
    op.create_index("ix_actividad_pagos_paid_at",         "actividad_pagos", ["paid_at"])


def downgrade() -> None:
    op.drop_table("actividad_pagos")
    op.drop_table("actividad_participantes")
    op.drop_table("actividades")
