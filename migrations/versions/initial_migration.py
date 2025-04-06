"""Initial migration

Revision ID: initial_migration
Create Date: 2025-03-26 23:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'initial_migration'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create transactions table
    op.create_table('transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wallet', sa.String(length=50), nullable=False),
        sa.Column('type', sa.String(length=10), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('counterparty', sa.String(length=255), nullable=True),
        sa.Column('balance', sa.Float(), nullable=True),
        sa.Column('balance_currency', sa.String(length=10), nullable=True),
        sa.Column('raw_message', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_transactions_wallet'), 'transactions', ['wallet'], unique=False)
    op.create_index(op.f('ix_transactions_currency'), 'transactions', ['currency'], unique=False)
    op.create_index(op.f('ix_transactions_type'), 'transactions', ['type'], unique=False)
    op.create_index(op.f('ix_transactions_timestamp'), 'transactions', ['timestamp'], unique=False)


def downgrade():
    # Drop indexes
    op.drop_index(op.f('ix_transactions_timestamp'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_type'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_currency'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_wallet'), table_name='transactions')
    
    # Drop transactions table
    op.drop_table('transactions')
