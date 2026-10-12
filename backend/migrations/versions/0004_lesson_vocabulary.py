"""Add lesson vocabulary and a stable per-user catalog key.

Revision ID: 0004_lesson_vocabulary
Revises: 0003_vocabulary_review_state
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_lesson_vocabulary"
down_revision = "0003_vocabulary_review_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lessons",
        sa.Column(
            "vocabulary",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "vocabulary_items",
        sa.Column("source_key", sa.String(length=180), nullable=True),
    )
    op.create_index(
        "uq_vocabulary_user_source",
        "vocabulary_items",
        ["user_id", "source_key"],
        unique=True,
    )


def downgrade() -> None:
    raise RuntimeError(
        "Lesson vocabulary and personal source keys are retained data; create a reviewed backup migration before downgrade."
    )
