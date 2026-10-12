from datetime import date, datetime, timezone
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    BigInteger,
    Index,
    UniqueConstraint,
    Date,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


def now_utc():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    first_name: Mapped[str] = mapped_column(String(100), default="Learner")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc
    )
    settings: Mapped["UserSettings"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )


class UserSettings(Base):
    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint(
            "daily_goal BETWEEN 5 AND 60", name="ck_user_settings_daily_goal"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    ui_language: Mapped[str] = mapped_column(String(8), default="ru")
    target_language: Mapped[str] = mapped_column(String(8), default="en")
    daily_goal: Mapped[int] = mapped_column(Integer, default=10)
    user: Mapped[User] = relationship(back_populates="settings")


class LearningEvent(Base):
    __tablename__ = "learning_events"
    __table_args__ = (
        Index("ix_learning_events_user_created", "user_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    lesson_id: Mapped[str] = mapped_column(String(80))
    exercise_id: Mapped[str] = mapped_column(String(80))
    answer: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc
    )


class LearningActivity(Base):
    """Idempotent, verified actions used for goals and daily streaks."""

    __tablename__ = "learning_activities"
    __table_args__ = (
        CheckConstraint(
            "activity_type IN ('exercise', 'vocabulary_review')",
            name="ck_learning_activities_type",
        ),
        UniqueConstraint(
            "user_id",
            "activity_date",
            "activity_type",
            "source_key",
            name="uq_learning_activity_source_per_day",
        ),
        Index("ix_learning_activities_user_date", "user_id", "activity_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    activity_date: Mapped[date] = mapped_column(Date)
    activity_type: Mapped[str] = mapped_column(String(24))
    source_key: Mapped[str] = mapped_column(String(180))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VocabularyItem(Base):
    __tablename__ = "vocabulary_items"
    __table_args__ = (
        Index("ix_vocabulary_items_user_due", "user_id", "next_review_at"),
        Index("uq_vocabulary_user_source", "user_id", "source_key", unique=True),
        CheckConstraint("length(word) > 0", name="ck_vocabulary_word_nonempty"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    word: Mapped[str] = mapped_column(String(120))
    translation: Mapped[str] = mapped_column(String(160))
    source_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    next_review_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc
    )
    successful_reviews: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    failed_reviews: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    consecutive_successes: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    interval_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    translation_revealed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_rating: Mapped[str | None] = mapped_column(String(8), nullable=True)


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint("length(slug) > 0", name="ck_courses_slug_nonempty"),
        CheckConstraint("length(source_language) = 2", name="ck_courses_source_lang"),
        CheckConstraint("length(target_language) = 2", name="ck_courses_target_lang"),
        CheckConstraint("length(level) BETWEEN 2 AND 8", name="ck_courses_level"),
        CheckConstraint("sort_order >= 0", name="ck_courses_sort_order"),
        Index("ix_courses_published_order", "is_published", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[dict] = mapped_column(JSON)
    description: Mapped[dict] = mapped_column(JSON)
    source_language: Mapped[str] = mapped_column(String(2), default="ru")
    target_language: Mapped[str] = mapped_column(String(2), default="en")
    level: Mapped[str] = mapped_column(String(8), default="A1")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    lessons: Mapped[list["Lesson"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Lesson.sort_order",
    )


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        CheckConstraint("length(slug) > 0", name="ck_lessons_slug_nonempty"),
        CheckConstraint("sort_order >= 0", name="ck_lessons_sort_order"),
        UniqueConstraint("course_id", "sort_order", name="uq_lessons_course_order"),
        Index("ix_lessons_course_available", "course_id", "is_available", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[dict] = mapped_column(JSON)
    description: Mapped[dict] = mapped_column(JSON)
    vocabulary: Mapped[list[dict]] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    course: Mapped[Course] = relationship(back_populates="lessons")
    exercises: Mapped[list["Exercise"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="Exercise.sort_order",
    )


class Exercise(Base):
    __tablename__ = "exercises"
    __table_args__ = (
        CheckConstraint(
            "exercise_type IN ('choice', 'text', 'word_order')",
            name="ck_exercises_type",
        ),
        CheckConstraint("sort_order >= 0", name="ck_exercises_sort_order"),
        UniqueConstraint("lesson_id", "sort_order", name="uq_exercises_lesson_order"),
        Index("ix_exercises_lesson_order", "lesson_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    exercise_type: Mapped[str] = mapped_column(String(16))
    instruction: Mapped[dict] = mapped_column(JSON)
    prompt: Mapped[dict] = mapped_column(JSON)
    # Validated, type-specific fields: choices, accepted strings, or ordered token IDs.
    public_data: Mapped[dict] = mapped_column(JSON)
    answer_data: Mapped[dict] = mapped_column(JSON)
    explanation: Mapped[dict] = mapped_column(JSON)
    hints: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    lesson: Mapped[Lesson] = relationship(back_populates="exercises")


class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_lesson_progress_user_lesson"),
        Index("ix_lesson_progress_user_completed", "user_id", "completed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc
    )
