"""Verified activity recording and dashboard aggregates (UTC calendar days)."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Course,
    Exercise,
    LearningActivity,
    LearningEvent,
    Lesson,
    LessonProgress,
    User,
    VocabularyItem,
)


def record_learning_activity(
    db: Session,
    user_id: int,
    activity_type: str,
    source_key: str,
    occurred_at: datetime,
) -> None:
    """Store one verified source action per UTC date; duplicate retries are no-ops."""
    occurred_at = (
        occurred_at.replace(tzinfo=timezone.utc)
        if occurred_at.tzinfo is None
        else occurred_at.astimezone(timezone.utc)
    )
    try:
        with db.begin_nested():
            db.add(
                LearningActivity(
                    user_id=user_id,
                    activity_date=occurred_at.date(),
                    activity_type=activity_type,
                    source_key=source_key,
                    occurred_at=occurred_at,
                )
            )
            db.flush()
    except IntegrityError:
        # The unique key makes concurrent retries safely idempotent.
        pass


def calculate_current_streak(active_dates: set[date], today: date) -> int:
    """Count consecutive active UTC dates ending today, or yesterday if today is quiet."""
    cursor = today if today in active_dates else today - timedelta(days=1)
    if cursor not in active_dates:
        return 0
    streak = 0
    while cursor in active_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def build_dashboard(db: Session, user: User, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    now = (
        now.replace(tzinfo=timezone.utc)
        if now.tzinfo is None
        else now.astimezone(timezone.utc)
    )
    today = now.date()
    first_day = today - timedelta(days=6)

    activity_rows = db.execute(
        select(
            LearningActivity.activity_date,
            LearningActivity.activity_type,
            func.count(LearningActivity.id),
        )
        .where(
            LearningActivity.user_id == user.id,
            LearningActivity.activity_date >= first_day,
            LearningActivity.activity_date <= today,
        )
        .group_by(LearningActivity.activity_date, LearningActivity.activity_type)
    ).all()
    by_day: dict[date, dict[str, int]] = {}
    for activity_date, kind, count in activity_rows:
        by_day.setdefault(
            activity_date, {"exercise_actions": 0, "vocabulary_review_actions": 0}
        )
        by_day[activity_date][
            "exercise_actions" if kind == "exercise" else "vocabulary_review_actions"
        ] = count
    recent = []
    for offset in range(7):
        day = first_day + timedelta(days=offset)
        counts = by_day.get(
            day, {"exercise_actions": 0, "vocabulary_review_actions": 0}
        )
        recent.append(
            {"date": day.isoformat(), **counts, "total_actions": sum(counts.values())}
        )
    today_counts = by_day.get(
        today, {"exercise_actions": 0, "vocabulary_review_actions": 0}
    )
    activity_dates = set(
        db.scalars(
            select(LearningActivity.activity_date)
            .where(
                LearningActivity.user_id == user.id,
                LearningActivity.activity_date <= today,
            )
            .distinct()
        )
    )

    course = db.scalar(
        select(Course).where(Course.slug == "english-a1", Course.is_published.is_(True))
    )
    lesson_count = completed_count = exercise_count = 0
    next_lesson = None
    course_unique_correct = 0
    if course:
        lessons = list(
            db.scalars(
                select(Lesson)
                .where(Lesson.course_id == course.id, Lesson.is_available.is_(True))
                .order_by(Lesson.sort_order, Lesson.id)
            )
        )
        lesson_count = len(lessons)
        completed_ids = set(
            db.scalars(
                select(LessonProgress.lesson_id).where(
                    LessonProgress.user_id == user.id
                )
            )
        )
        completed_count = sum(lesson.id in completed_ids for lesson in lessons)
        if lessons:
            next_lesson = next(
                (lesson for lesson in lessons if lesson.id not in completed_ids), None
            )
        exercise_count = int(
            db.scalar(
                select(func.count(Exercise.id))
                .join(Lesson)
                .where(
                    Lesson.course_id == course.id,
                    Lesson.is_available.is_(True),
                    Exercise.is_available.is_(True),
                )
            )
            or 0
        )
        course_unique_correct = int(
            db.scalar(
                select(func.count()).select_from(
                    select(LearningEvent.lesson_id, LearningEvent.exercise_id)
                    .join(Lesson, Lesson.slug == LearningEvent.lesson_id)
                    .where(
                        Lesson.course_id == course.id,
                        LearningEvent.user_id == user.id,
                        LearningEvent.is_correct.is_(True),
                    )
                    .distinct()
                    .subquery()
                )
            )
            or 0
        )

    attempts = int(
        db.scalar(
            select(func.count(LearningEvent.id)).where(LearningEvent.user_id == user.id)
        )
        or 0
    )
    correct_submissions = int(
        db.scalar(
            select(func.count(LearningEvent.id)).where(
                LearningEvent.user_id == user.id, LearningEvent.is_correct.is_(True)
            )
        )
        or 0
    )
    unique_correct = int(
        db.scalar(
            select(func.count()).select_from(
                select(LearningEvent.lesson_id, LearningEvent.exercise_id)
                .where(
                    LearningEvent.user_id == user.id, LearningEvent.is_correct.is_(True)
                )
                .distinct()
                .subquery()
            )
        )
        or 0
    )
    due_words = int(
        db.scalar(
            select(func.count(VocabularyItem.id)).where(
                VocabularyItem.user_id == user.id, VocabularyItem.next_review_at <= now
            )
        )
        or 0
    )
    vocab_rows = db.scalars(
        select(VocabularyItem).where(VocabularyItem.user_id == user.id)
    ).all()
    review_submissions = sum(
        item.successful_reviews + item.failed_reviews for item in vocab_rows
    )
    completed_vocab = db.execute(
        select(Lesson.vocabulary)
        .join(LessonProgress, LessonProgress.lesson_id == Lesson.id)
        .where(LessonProgress.user_id == user.id)
    ).all()
    learned_words = {
        str(entry.get("word", "")).casefold()
        for (words,) in completed_vocab
        for entry in (words or [])
        if entry.get("word")
    }
    goal = user.settings.daily_goal if user.settings else 10
    today_total = sum(today_counts.values())
    return {
        "timezone": "UTC",
        "date": today.isoformat(),
        "course": None
        if course is None
        else {
            "id": course.slug,
            "title": course.title,
            "completed_lessons": completed_count,
            "total_lessons": lesson_count,
            "progress_percent": round(completed_count / lesson_count * 100)
            if lesson_count
            else 0,
            "completed_exercises": course_unique_correct,
            "total_exercises": exercise_count,
            "next_lesson": None
            if next_lesson is None
            else {
                "id": next_lesson.slug,
                "title": next_lesson.title,
                "description": next_lesson.description,
            },
        },
        "today": {
            **today_counts,
            "total_actions": today_total,
            "goal": goal,
            "goal_reached": today_total >= goal,
        },
        "current_streak_days": calculate_current_streak(activity_dates, today),
        "recent_activity": recent,
        "stats": {
            "exercises_attempted": attempts,
            "correct_answer_submissions": correct_submissions,
            "unique_exercises_answered_correctly": unique_correct,
            "lessons_completed": completed_count,
            "vocabulary_items_due": due_words,
            "vocabulary_review_submissions": review_submissions,
            "unique_vocabulary_words_learned": len(learned_words),
        },
    }
