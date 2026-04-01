"""documentos de contexto para el agente — personal e institucional

Revision ID: 0006_context_documents
Revises: 0005_reminders
Create Date: 2026-03-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_context_documents"
down_revision: Union[str, None] = "0005_reminders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "context_documents",
        sa.Column("id",                sa.Integer(),                nullable=False),
        sa.Column("teacher_id",        sa.Integer(),                nullable=True),
        sa.Column("scope",             sa.String(20),               nullable=False, server_default="personal"),
        sa.Column("category",          sa.String(30),               nullable=False, server_default="other"),
        sa.Column("title",             sa.String(120),              nullable=False),
        sa.Column("content",           sa.Text(),                   nullable=False),
        sa.Column("source_type",       sa.String(20),               nullable=False, server_default="text"),
        sa.Column("original_filename", sa.String(255),              nullable=True),
        sa.Column("hint",              sa.Text(),                   nullable=True),
        sa.Column("created_at",        sa.DateTime(timezone=True),  nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ctx_docs_teacher_scope", "context_documents", ["teacher_id", "scope"])
    op.create_index("ix_ctx_docs_category",      "context_documents", ["category"])
    # GIN index para full-text search en español
    op.execute(
        "CREATE INDEX ix_ctx_docs_fts ON context_documents "
        "USING GIN (to_tsvector('spanish', coalesce(title,'') || ' ' || coalesce(content,'')))"
    )


def downgrade() -> None:
    op.drop_index("ix_ctx_docs_fts",          table_name="context_documents")
    op.drop_index("ix_ctx_docs_category",     table_name="context_documents")
    op.drop_index("ix_ctx_docs_teacher_scope",table_name="context_documents")
    op.drop_table("context_documents")
