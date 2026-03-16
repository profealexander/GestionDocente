"""create student_representatives, drop guardian_id from students

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-03-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'student_representatives',
        sa.Column('id',                sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('student_id',        sa.Integer(), sa.ForeignKey('students.id',  ondelete='CASCADE'), nullable=False),
        sa.Column('person_id',         sa.Integer(), sa.ForeignKey('people.id',    ondelete='CASCADE'), nullable=False),
        sa.Column('relationship_type', sa.String(),  nullable=True),
        sa.Column('is_primary_notify', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('status',            sa.String(),  nullable=False, server_default='active'),
    )
    op.create_index('ix_studrep_student_id', 'student_representatives', ['student_id'])
    op.create_index('ix_studrep_person_id',  'student_representatives', ['person_id'])

    # Migrate existing guardian_id data
    op.execute("""
        INSERT INTO student_representatives (student_id, person_id, is_primary_notify, status)
        SELECT id, guardian_id, true, 'active'
        FROM students
        WHERE guardian_id IS NOT NULL
    """)

    # Drop guardian_id from students
    op.drop_column('students', 'guardian_id')

    # Fix role values: map Spanish → English to match check constraint
    op.execute("UPDATE people SET role = 'student'              WHERE role = 'estudiante'")
    op.execute("UPDATE people SET role = 'teacher'              WHERE role = 'docente'")
    op.execute("UPDATE people SET role = 'executive'            WHERE role = 'directivo'")
    op.execute("UPDATE people SET role = 'admin'                WHERE role = 'administrativo'")
    op.execute("UPDATE people SET role = 'parent'               WHERE role = 'representante'")
    op.execute("UPDATE people SET role = 'legal_representative' WHERE role = 'representante_legal'")


def downgrade() -> None:
    op.add_column('students', sa.Column('guardian_id', sa.Integer(), sa.ForeignKey('people.id'), nullable=True))
    op.execute("""
        UPDATE students s
        SET guardian_id = sr.person_id
        FROM student_representatives sr
        WHERE sr.student_id = s.id AND sr.is_primary_notify = true
    """)
    op.drop_index('ix_studrep_student_id', table_name='student_representatives')
    op.drop_index('ix_studrep_person_id',  table_name='student_representatives')
    op.drop_table('student_representatives')
