"""Add database-backed courses, lessons, exercises and lesson progress.

Revision ID: 0002_learning_engine
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_learning_engine"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("courses"):
        op.create_table(
            "courses",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("slug", sa.String(length=80), nullable=False),
            sa.Column("title", sa.JSON(), nullable=False),
            sa.Column("description", sa.JSON(), nullable=False),
            sa.Column("source_language", sa.String(length=2), nullable=False),
            sa.Column("target_language", sa.String(length=2), nullable=False),
            sa.Column("level", sa.String(length=8), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("is_published", sa.Boolean(), nullable=False),
            sa.CheckConstraint("length(slug) > 0", name="ck_courses_slug_nonempty"),
            sa.CheckConstraint(
                "length(source_language) = 2", name="ck_courses_source_lang"
            ),
            sa.CheckConstraint(
                "length(target_language) = 2", name="ck_courses_target_lang"
            ),
            sa.CheckConstraint(
                "length(level) BETWEEN 2 AND 8", name="ck_courses_level"
            ),
            sa.CheckConstraint("sort_order >= 0", name="ck_courses_sort_order"),
            sa.UniqueConstraint("slug", name="uq_courses_slug"),
        )
    if not _has_table("lessons"):
        op.create_table(
            "lessons",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("course_id", sa.Integer(), nullable=False),
            sa.Column("slug", sa.String(length=80), nullable=False),
            sa.Column("title", sa.JSON(), nullable=False),
            sa.Column("description", sa.JSON(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("is_available", sa.Boolean(), nullable=False),
            sa.CheckConstraint("length(slug) > 0", name="ck_lessons_slug_nonempty"),
            sa.CheckConstraint("sort_order >= 0", name="ck_lessons_sort_order"),
            sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("slug", name="uq_lessons_slug"),
            sa.UniqueConstraint(
                "course_id", "sort_order", name="uq_lessons_course_order"
            ),
        )
    if not _has_table("exercises"):
        op.create_table(
            "exercises",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("lesson_id", sa.Integer(), nullable=False),
            sa.Column("slug", sa.String(length=80), nullable=False),
            sa.Column("exercise_type", sa.String(length=16), nullable=False),
            sa.Column("instruction", sa.JSON(), nullable=False),
            sa.Column("prompt", sa.JSON(), nullable=False),
            sa.Column("public_data", sa.JSON(), nullable=False),
            sa.Column("answer_data", sa.JSON(), nullable=False),
            sa.Column("explanation", sa.JSON(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("is_available", sa.Boolean(), nullable=False),
            sa.CheckConstraint(
                "exercise_type IN ('choice', 'text', 'word_order')",
                name="ck_exercises_type",
            ),
            sa.CheckConstraint("sort_order >= 0", name="ck_exercises_sort_order"),
            sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("slug", name="uq_exercises_slug"),
            sa.UniqueConstraint(
                "lesson_id", "sort_order", name="uq_exercises_lesson_order"
            ),
        )
    if not _has_table("lesson_progress"):
        op.create_table(
            "lesson_progress",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("lesson_id", sa.Integer(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "user_id", "lesson_id", name="uq_lesson_progress_user_lesson"
            ),
        )
    _create_index_if_missing(
        "courses", "ix_courses_published_order", ["is_published", "sort_order"]
    )
    _create_index_if_missing(
        "lessons",
        "ix_lessons_course_available",
        ["course_id", "is_available", "sort_order"],
    )
    _create_index_if_missing(
        "exercises", "ix_exercises_lesson_order", ["lesson_id", "sort_order"]
    )
    _create_index_if_missing(
        "lesson_progress",
        "ix_lesson_progress_user_completed",
        ["user_id", "completed_at"],
    )


def _create_index_if_missing(table_name: str, name: str, columns: list[str]) -> None:
    indexes = {
        index["name"] for index in inspect(op.get_bind()).get_indexes(table_name)
    }
    if name not in indexes:
        op.create_index(name, table_name, columns)


def downgrade() -> None:
    raise RuntimeError(
        "This migration adds course content and user progress. Downgrade could delete data; "
        "back up and use a reviewed forward migration instead."
    )
