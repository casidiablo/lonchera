"""added sync deletion flag

Revision ID: a764c4788e16
Revises: 0001
Create Date: 2026-03-27 10:38:33.106055

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a764c4788e16"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("sync_delete_with_lunchmoney", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("sync_delete_with_lunchmoney")
