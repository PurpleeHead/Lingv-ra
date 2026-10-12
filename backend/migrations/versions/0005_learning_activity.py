"""Record verified daily learning activity for goals and streaks.

Revision ID: 0005_learning_activity
Revises: 0004_lesson_vocabulary
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_learning_activity"
down_revision = "0004_lesson_vocabulary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("activity_type", sa.String(length=24), nullable=False),
        sa.Column("source_key", sa.String(length=180), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "activity_type IN ('exercise', 'vocabulary_review')",
            name="ck_learning_activities_type",
        ),
        sa.UniqueConstraint(
            "user_id",
            "activity_date",
            "activity_type",
            "source_key",
            name="uq_learning_activity_source_per_day",
        ),
    )
    op.create_index(
        "ix_learning_activities_user_date",
        "learning_activities",
        ["user_id", "activity_date"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Daily activity is retained user data; create a reviewed backup migration before downgrade."
    )
