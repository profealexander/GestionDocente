"""replace phone/callmebot_apikey on people with whatsapp_contacts table

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-03-16 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'whatsapp_contacts',
        sa.Column('id',               sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column('person_id',        sa.Integer(),  sa.ForeignKey('people.id', ondelete='CASCADE'), nullable=False),
        sa.Column('phone',            sa.String(),   nullable=False),
        sa.Column('callmebot_apikey', sa.String(),   nullable=True),
        sa.Column('label',            sa.String(),   nullable=True),   # "celular", "trabajo", etc.
        sa.Column('is_primary',       sa.Boolean(),  nullable=False, server_default='false'),
        sa.Column('status',           sa.String(),   nullable=False, server_default='active'),
    )
    op.create_index('ix_whatsapp_contacts_person_id', 'whatsapp_contacts', ['person_id'])

    # Migrate existing data from people.phone → whatsapp_contacts
    op.execute("""
        INSERT INTO whatsapp_contacts (person_id, phone, callmebot_apikey, is_primary, status)
        SELECT id, phone, callmebot_apikey, true, 'active'
        FROM people
        WHERE phone IS NOT NULL
    """)

    # Remove columns from people
    op.drop_column('people', 'phone')
    op.drop_column('people', 'callmebot_apikey')


def downgrade() -> None:
    op.add_column('people', sa.Column('phone',            sa.String(), nullable=True))
    op.add_column('people', sa.Column('callmebot_apikey', sa.String(), nullable=True))
    op.drop_index('ix_whatsapp_contacts_person_id', table_name='whatsapp_contacts')
    op.drop_table('whatsapp_contacts')
