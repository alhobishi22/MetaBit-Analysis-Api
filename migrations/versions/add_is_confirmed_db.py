"""Add is_confirmed_db column

Revision ID: add_is_confirmed_db
Revises: 
Create Date: 2025-03-27 02:34:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_is_confirmed_db'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Add is_confirmed_db column to transactions table
    op.add_column('transactions', sa.Column('is_confirmed_db', sa.Boolean(), nullable=True, server_default='0'))

def downgrade():
    # Drop is_confirmed_db column from transactions table
    op.drop_column('transactions', 'is_confirmed_db')
