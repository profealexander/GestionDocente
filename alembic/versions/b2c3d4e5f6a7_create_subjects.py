"""create_subjects

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-12 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SUBJECTS = [
    # Básica Media y Superior
    ("Lengua y Literatura",          "Lengua y Literatura",              "basica"),
    ("Matemática",                   "Matemáticas",                      "basica"),
    ("Ciencias Sociales",            "Ciencias Sociales",                "basica"),
    ("Ciencias Naturales",           "Ciencias Naturales",               "basica"),
    ("Educación Cultural y Artística","Educación Cultural y Artística",  "basica"),
    ("Educación Física",             "Educación Física",                  "basica"),
    ("Lengua Extranjera",            "Inglés",                           "basica"),
    # Bachillerato - Tronco Común
    ("Matemática",                   "Matemática",                       "bachillerato"),
    ("Ciencias Naturales",           "Física",                           "bachillerato"),
    ("Ciencias Naturales",           "Química",                          "bachillerato"),
    ("Ciencias Naturales",           "Biología",                         "bachillerato"),
    ("Ciencias Sociales",            "Historia",                         "bachillerato"),
    ("Ciencias Sociales",            "Educación para la Ciudadanía",     "bachillerato"),
    ("Ciencias Sociales",            "Filosofía",                        "bachillerato"),
    ("Lengua y Literatura",          "Lengua y Literatura",              "bachillerato"),
    ("Lengua Extranjera",            "Inglés",                           "bachillerato"),
    ("Educación Cultural y Artística","Educación Cultural y Artística",  "bachillerato"),
    ("Educación Física",             "Educación Física",                  "bachillerato"),
    ("Módulo Interdisciplinar",      "Emprendimiento y Gestión",         "bachillerato"),
]


def upgrade() -> None:
    op.create_table(
        'subjects',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('area', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('subnivel', sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'subnivel', name='uq_subject_name_subnivel'),
    )

    op.bulk_insert(
        sa.table('subjects',
            sa.column('area', sa.String),
            sa.column('name', sa.String),
            sa.column('subnivel', sa.String),
        ),
        [{"area": a, "name": n, "subnivel": s} for a, n, s in SUBJECTS],
    )

    # Add subject_id FK to homework
    op.add_column('homework', sa.Column('subject_id', sa.Integer(), nullable=True))
    op.create_foreign_key('homework_subject_id_fkey', 'homework', 'subjects', ['subject_id'], ['id'])
    op.drop_column('homework', 'subject')


def downgrade() -> None:
    op.drop_constraint('homework_subject_id_fkey', 'homework', type_='foreignkey')
    op.drop_column('homework', 'subject_id')
    op.add_column('homework', sa.Column('subject', sa.String(length=100), nullable=True))
    op.drop_table('subjects')
