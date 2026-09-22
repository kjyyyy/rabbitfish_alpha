"""inner holdout metrics on trials

Revision ID: 4002058acc4e
Revises: 803d3db11492
Create Date: 2026-09-21 18:22:12.230417
"""
from alembic import op
import sqlalchemy as sa


revision = '4002058acc4e'
down_revision = '803d3db11492'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('trials', schema=None) as batch_op:
        batch_op.add_column(sa.Column('inner_oos_ic', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('inner_oos_t', sa.Float(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('trials', schema=None) as batch_op:
        batch_op.drop_column('inner_oos_t')
        batch_op.drop_column('inner_oos_ic')

