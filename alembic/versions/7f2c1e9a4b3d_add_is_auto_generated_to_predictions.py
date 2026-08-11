"""add is_auto_generated to predictions and bonus_predictions

Revision ID: 7f2c1e9a4b3d
Revises: 45de3e136937
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f2c1e9a4b3d'
down_revision: Union[str, Sequence[str], None] = '45de3e136937'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'predictions',
        sa.Column('is_auto_generated', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'bonus_predictions',
        sa.Column('is_auto_generated', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Note: intentionally leaving server_default in place rather than dropping it —
    # SQLite doesn't support ALTER COLUMN ... DROP DEFAULT, and there's no need to
    # drop it since the app always sets is_auto_generated explicitly anyway.


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('bonus_predictions', 'is_auto_generated')
    op.drop_column('predictions', 'is_auto_generated')
