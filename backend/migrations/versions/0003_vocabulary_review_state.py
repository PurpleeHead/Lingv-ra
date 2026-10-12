"""Add per-user spaced-repetition state to existing vocabulary rows.

Revision ID: 0003_vocabulary_review_state
Revises: 0002_learning_engine
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_vocabulary_review_state"
down_revision = "0002_learning_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Server defaults backfill existing rows without touching their vocabulary,
    # ownership, next_review_at, or any learning data.
    op.add_column(
        "vocabulary_items",
        sa.Column(
            "successful_reviews", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "vocabulary_items",
        sa.Column("failed_reviews", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "vocabulary_items",
        sa.Column(
            "consecutive_successes", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "vocabulary_items",
        sa.Column("interval_days", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "vocabulary_items",
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "vocabulary_items", sa.Column("last_rating", sa.String(length=8), nullable=True)
    )
    op.add_column(
        "vocabulary_items",
        sa.Column("translation_revealed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Dropping these columns discards review history for vocabulary items.
    raise RuntimeError(
        "Vocabulary review state is user data; back up and write a reviewed data migration instead of downgrading."
    )
