"""drop person_roles, add teacher_positions

Revision ID: b3c4d5e6f7a8
Revises: a7b8c9d0e1f2
Create Date: 2026-03-16

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('person_roles')

    op.create_table(
        'teacher_positions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('teacher_id', sa.Integer, sa.ForeignKey('teachers.id'), nullable=False),
        sa.Column('position_type', sa.String(20), nullable=False),  # tutor|jefe_area|jefe_subnivel|comision|cargo
        sa.Column('grade_id', sa.Integer, sa.ForeignKey('grades.id'), nullable=True),
        sa.Column('subnivel', sa.String(20), nullable=True),        # inicial|basica|media|bachillerato
        sa.Column('area', sa.String(100), nullable=True),
        sa.Column('detail', sa.String(200), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
    )


def downgrade() -> None:
    op.drop_table('teacher_positions')

    op.create_table(
        'person_roles',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('person_id', sa.Integer, sa.ForeignKey('people.id'), nullable=False),
        sa.Column('role', sa.String, nullable=False),
        sa.Column('is_primary', sa.Boolean, nullable=False, server_default='false'),
    )
