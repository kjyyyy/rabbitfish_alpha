"""record which code version produced each run

Revision ID: 803d3db11492
Revises: 568389289a95
Create Date: 2026-09-21 18:07:08.209922
"""
from alembic import op
import sqlalchemy as sa


revision = '803d3db11492'
down_revision = '568389289a95'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default is required: SQLite cannot add a NOT NULL column to a table
    # that already has rows without one, and every existing run predates the
    # column - they genuinely do not know which version produced them.
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("alphalab_version", sa.String(length=32),
                                      nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("alphalab_version")
