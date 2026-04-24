"""baseline — create all tables

Revision ID: 0001_baseline
Revises:
Create Date: 2026-03-16

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = '0001_baseline'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pg_trgm — needed for fuzzy subject search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        'people',
        sa.Column('id',                   sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column('first_name',           sa.String,      nullable=False),
        sa.Column('middle_name',          sa.String,      nullable=True),
        sa.Column('last_name',            sa.String,      nullable=False),
        sa.Column('second_last_name',     sa.String,      nullable=True),
        sa.Column('national_id',          sa.String,      nullable=True),
        sa.Column('passport',             sa.String,      nullable=True),
        sa.Column('title',                sa.String,      nullable=True),
        sa.Column('role',                 sa.String,      nullable=False),
        sa.Column('current_position',     sa.String,      nullable=True),
        sa.Column('current_institution',  sa.String,      nullable=True),
        sa.Column('previous_institution', sa.String,      nullable=True),
        sa.Column('email',                sa.String,      nullable=True),
        sa.Column('telegram_handle',      sa.String,      nullable=True),
        sa.Column('status',               sa.String,      nullable=False, server_default='active'),
    )

    op.create_table(
        'grades',
        sa.Column('id',         sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column('name',       sa.String(30),  nullable=False, unique=True),
        sa.Column('sort_order', sa.Integer,     nullable=False),
        sa.Column('level',      sa.String(20),  nullable=True),
        sa.Column('sublevel',   sa.String(20),  nullable=True),
    )

    op.create_table(
        'subjects',
        sa.Column('id',       sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column('area',     sa.String(100), nullable=False),
        sa.Column('name',     sa.String(100), nullable=False),
        sa.Column('sublevel', sa.String(20),  nullable=False),
    )

    op.create_table(
        'students',
        sa.Column('id',        sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('person_id', sa.Integer, sa.ForeignKey('people.id'),  nullable=True),
        sa.Column('grade_id',  sa.Integer, sa.ForeignKey('grades.id'),  nullable=False),
        sa.Column('section',   sa.String,  nullable=False),
        sa.Column('status',    sa.String,  nullable=False, server_default='active'),
    )

    op.create_table(
        'attendance',
        sa.Column('id',          sa.Integer,  primary_key=True, autoincrement=True),
        sa.Column('student_id',  sa.Integer,  sa.ForeignKey('students.id'), nullable=True),
        sa.Column('date',        sa.Date,     nullable=False),
        sa.Column('status',      sa.String(1),nullable=False),
        sa.Column('notes',       sa.String,   nullable=True),
        sa.Column('recorded_by', sa.Integer,  sa.ForeignKey('people.id'), nullable=True),
        sa.Column('created_at',  sa.DateTime, server_default=sa.text('now()'), nullable=False),
    )

    op.create_table(
        'teachers',
        sa.Column('id',          sa.Integer,    primary_key=True, autoincrement=True),
        sa.Column('person_id',   sa.Integer,    sa.ForeignKey('people.id'), nullable=False, unique=True),
        sa.Column('telegram_id', sa.BigInteger, nullable=True, unique=True),
        sa.Column('is_active',   sa.Boolean,    nullable=False, server_default='true'),
    )

    op.create_table(
        'homework',
        sa.Column('id',              sa.Integer,                    primary_key=True, autoincrement=True),
        sa.Column('homework',        sa.Text,                       nullable=False),
        sa.Column('grade_id',        sa.Integer,                    sa.ForeignKey('grades.id'),   nullable=False),
        sa.Column('subject_id',      sa.Integer,                    sa.ForeignKey('subjects.id'), nullable=True),
        sa.Column('teacher_id',      sa.Integer,                    sa.ForeignKey('teachers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('submission_date', sa.DateTime(timezone=True),    server_default=sa.text('now()'), nullable=False),
        sa.Column('delivery_date',   sa.DateTime(timezone=True),    nullable=True),
        sa.Column('is_open',         sa.Boolean,                    nullable=False, server_default='true'),
        sa.Column('sequence_num',    sa.Integer,                    nullable=False, server_default='0'),
        sa.Column('trimester_num',   sa.Integer,                    nullable=False, server_default='0'),
    )

    op.create_table(
        'homework_submissions',
        sa.Column('id',          sa.Integer,  primary_key=True, autoincrement=True),
        sa.Column('homework_id', sa.Integer,  sa.ForeignKey('homework.id',  ondelete='CASCADE'), nullable=False),
        sa.Column('student_id',  sa.Integer,  sa.ForeignKey('students.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status',      sa.String(20), nullable=False, server_default='missing'),
        sa.Column('reported_at', sa.DateTime, server_default=sa.text('now()'), nullable=False),
    )

    op.create_table(
        'schedules',
        sa.Column('id',          sa.Integer,    primary_key=True, autoincrement=True),
        sa.Column('teacher_id',  sa.Integer,    sa.ForeignKey('teachers.id'), nullable=False),
        sa.Column('day_of_week', sa.SmallInteger, nullable=False),
        sa.Column('period_num',  sa.SmallInteger, nullable=False),
        sa.Column('start_time',  sa.String(5),  nullable=False),
        sa.Column('end_time',    sa.String(5),  nullable=False),
        sa.Column('grade_id',    sa.Integer,    sa.ForeignKey('grades.id'),   nullable=False),
        sa.Column('subject_id',  sa.Integer,    sa.ForeignKey('subjects.id'), nullable=False),
        sa.Column('is_active',   sa.Boolean,    nullable=False, server_default='true'),
    )

    op.create_table(
        'teacher_positions',
        sa.Column('id',            sa.Integer,     primary_key=True, autoincrement=True),
        sa.Column('teacher_id',    sa.Integer,     sa.ForeignKey('teachers.id'), nullable=False),
        sa.Column('position_type', sa.String(20),  nullable=False),
        sa.Column('grade_id',      sa.Integer,     sa.ForeignKey('grades.id'), nullable=True),
        sa.Column('subnivel',      sa.String(20),  nullable=True),
        sa.Column('area',          sa.String(100), nullable=True),
        sa.Column('detail',        sa.String(200), nullable=True),
        sa.Column('is_active',     sa.Boolean,     nullable=False, server_default='true'),
    )

    op.create_table(
        'student_representatives',
        sa.Column('id',                sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('student_id',        sa.Integer, sa.ForeignKey('students.id', ondelete='CASCADE'), nullable=False),
        sa.Column('person_id',         sa.Integer, sa.ForeignKey('people.id',   ondelete='CASCADE'), nullable=False),
        sa.Column('relationship_type', sa.String,  nullable=True),
        sa.Column('is_primary_notify', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('status',            sa.String,  nullable=False, server_default='active'),
    )

    op.create_table(
        'whatsapp_contacts',
        sa.Column('id',               sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('person_id',        sa.Integer, sa.ForeignKey('people.id', ondelete='CASCADE'), nullable=False),
        sa.Column('phone',            sa.String,  nullable=False),
        sa.Column('callmebot_apikey', sa.String,  nullable=True),
        sa.Column('label',            sa.String,  nullable=True),
        sa.Column('is_primary',       sa.Boolean, nullable=False, server_default='false'),
        sa.Column('status',           sa.String,  nullable=False, server_default='active'),
    )


def downgrade() -> None:
    op.drop_table('whatsapp_contacts')
    op.drop_table('student_representatives')
    op.drop_table('teacher_positions')
    op.drop_table('schedules')
    op.drop_table('homework_submissions')
    op.drop_table('homework')
    op.drop_table('teachers')
    op.drop_table('attendance')
    op.drop_table('students')
    op.drop_table('subjects')
    op.drop_table('grades')
    op.drop_table('people')
