"""Add authored two-level exercise hints.

Revision ID: 0006_exercise_hints
Revises: 0005_learning_activity
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_exercise_hints"
down_revision = "0005_learning_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exercises", sa.Column("hints", sa.JSON(), nullable=True))


def downgrade() -> None:
    raise RuntimeError(
        "Exercise hints are retained course content; use a reviewed backup migration before downgrade."
    )
