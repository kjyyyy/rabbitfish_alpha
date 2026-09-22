"""library factor passes and fingerprint

Revision ID: a1b2c3d4e5f6
Revises: 9d011d75fa42
Create Date: 2026-09-23 00:15:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = '9d011d75fa42'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('library_factors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('passes', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('fingerprint', sa.String(length=32), nullable=False,
                                      server_default=''))
        batch_op.create_index('ix_library_factors_fingerprint', ['fingerprint'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('library_factors', schema=None) as batch_op:
        batch_op.drop_index('ix_library_factors_fingerprint')
        batch_op.drop_column('fingerprint')
        batch_op.drop_column('passes')
