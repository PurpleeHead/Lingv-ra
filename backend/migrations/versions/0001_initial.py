"""Create initial Lingvéra learning tables.

Revision ID: 0001_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("telegram_id", sa.BigInteger(), nullable=False),
            sa.Column(
                "first_name",
                sa.String(length=100),
                nullable=False,
                server_default="Learner",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
        )
    existing = set(inspect(op.get_bind()).get_table_names())
    if "user_settings" not in existing:
        op.create_table(
            "user_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column(
                "ui_language", sa.String(length=8), nullable=False, server_default="ru"
            ),
            sa.Column(
                "target_language",
                sa.String(length=8),
                nullable=False,
                server_default="en",
            ),
            sa.Column("daily_goal", sa.Integer(), nullable=False, server_default="10"),
            sa.CheckConstraint(
                "daily_goal BETWEEN 5 AND 60", name="ck_user_settings_daily_goal"
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", name="uq_user_settings_user_id"),
        )
    existing = set(inspect(op.get_bind()).get_table_names())
    if "learning_events" not in existing:
        op.create_table(
            "learning_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("lesson_id", sa.String(length=80), nullable=False),
            sa.Column("exercise_id", sa.String(length=80), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("is_correct", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
    existing = set(inspect(op.get_bind()).get_table_names())
    if "vocabulary_items" not in existing:
        op.create_table(
            "vocabulary_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("word", sa.String(length=120), nullable=False),
            sa.Column("translation", sa.String(length=160), nullable=False),
            sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("length(word) > 0", name="ck_vocabulary_word_nonempty"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
    _create_index_if_missing(
        "learning_events", "ix_learning_events_user_created", ["user_id", "created_at"]
    )
    _create_index_if_missing(
        "vocabulary_items",
        "ix_vocabulary_items_user_due",
        ["user_id", "next_review_at"],
    )


def _create_index_if_missing(table_name, index_name, columns):
    if table_name not in inspect(op.get_bind()).get_table_names():
        return
    existing_indexes = {
        index["name"] for index in inspect(op.get_bind()).get_indexes(table_name)
    }
    if index_name not in existing_indexes:
        op.create_index(index_name, table_name, columns)


def downgrade():
    raise RuntimeError(
        "The baseline migration contains user data and is intentionally irreversible. "
        "Back up the database and use a reviewed data migration instead of downgrading."
    )
