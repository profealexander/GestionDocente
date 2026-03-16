"""add sequence_num trimester_num to homework and homework_submissions table

Revision ID: 10993455dc81
Revises: c3d4e5f6a7b8
Create Date: 2026-03-13 22:54:45.311724

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10993455dc81'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add sequence_num and trimester_num to homework table
    op.add_column('homework', sa.Column('sequence_num', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('homework', sa.Column('trimester_num', sa.Integer(), nullable=False, server_default='0'))

    # Create homework_submissions table
    op.create_table(
        'homework_submissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('homework_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='missing'),
        sa.Column('reported_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['homework_id'], ['homework.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('homework_submissions')
    op.drop_column('homework', 'trimester_num')
    op.drop_column('homework', 'sequence_num')
