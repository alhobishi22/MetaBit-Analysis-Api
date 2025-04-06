"""Add transaction_id and is_confirmed columns to transactions table

Revision ID: add_transaction_id_and_confirmation
Revises: 
Create Date: 2025-03-27 00:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
import uuid


# revision identifiers, used by Alembic.
revision = 'add_transaction_id_and_confirmation'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add transaction_id column
    op.add_column('transactions', sa.Column('transaction_id', sa.String(36), nullable=True))
    op.create_unique_constraint('uq_transaction_id', 'transactions', ['transaction_id'])
    
    # Add is_confirmed column
    op.add_column('transactions', sa.Column('is_confirmed', sa.Boolean(), nullable=True, server_default='0'))
    
    # Generate unique transaction_id for existing records
    conn = op.get_bind()
    transactions = conn.execute('SELECT id FROM transactions').fetchall()
    for tx in transactions:
        tx_id = str(uuid.uuid4())[:8]
        conn.execute(f"UPDATE transactions SET transaction_id = '{tx_id}' WHERE id = {tx[0]}")


def downgrade():
    # Remove is_confirmed column
    op.drop_column('transactions', 'is_confirmed')
    
    # Remove transaction_id column and its constraint
    op.drop_constraint('uq_transaction_id', 'transactions', type_='unique')
    op.drop_column('transactions', 'transaction_id')
