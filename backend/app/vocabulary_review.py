"""Personal vocabulary bootstrap and deterministic review scheduling."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content import VOCABULARY
from app.models import Lesson, LessonProgress, User, VocabularyItem
from app.schemas import ReviewRating
from app.activity import record_learning_activity


@dataclass(frozen=True)
class ReviewSchedule:
    successful_reviews: int
    failed_reviews: int
    consecutive_successes: int
    interval_days: int
    next_review_at: datetime


def as_utc(value: datetime) -> datetime:
    """Treat naive timestamps (returned by SQLite) as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def ensure_user_vocabulary(db: Session, user_id: int) -> None:
    # Serialize lazy bootstrap for the same learner on PostgreSQL. Other users
    # can still initialize their own vocabulary concurrently.
    db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    existing = list(
        db.scalars(select(VocabularyItem).where(VocabularyItem.user_id == user_id))
    )
    by_source = {item.source_key: item for item in existing if item.source_key}
    # Assign stable keys to the original four seed words in place, preserving
    # their IDs, review history, and schedules for learners already using them.
    for catalog_item in VOCABULARY:
        key = f"legacy:{catalog_item['word']}"
        if key in by_source:
            continue
        prior = next(
            (
                item
                for item in existing
                if item.source_key is None
                and item.word == catalog_item["word"]
                and item.translation == catalog_item["translation"]
            ),
            None,
        )
        if prior is not None:
            prior.source_key = key
            by_source[key] = prior
        else:
            item = VocabularyItem(
                user_id=user_id,
                source_key=key,
                word=catalog_item["word"],
                translation=catalog_item["translation"],
            )
            db.add(item)
            by_source[key] = item
            existing.append(item)

    # A lesson's words enter personal review only after it is completed. This
    # also safely backfills words for lessons completed before this release.
    rows = db.execute(
        select(Lesson.slug, Lesson.vocabulary)
        .join(LessonProgress, LessonProgress.lesson_id == Lesson.id)
        .where(LessonProgress.user_id == user_id)
    ).all()
    for lesson_slug, vocabulary in rows:
        for entry in vocabulary or []:
            key = f"lesson:{lesson_slug}:{entry['slug']}"
            already_personal = any(
                item.word.casefold() == entry["word"].casefold() for item in existing
            )
            if key not in by_source and not already_personal:
                item = VocabularyItem(
                    user_id=user_id,
                    source_key=key,
                    word=entry["word"],
                    translation=entry["translation"],
                )
                db.add(item)
                by_source[key] = item
                existing.append(item)
    db.commit()


def add_lesson_vocabulary(db: Session, user_id: int, lesson: Lesson) -> None:
    existing = list(
        db.scalars(select(VocabularyItem).where(VocabularyItem.user_id == user_id))
    )
    by_source = {item.source_key: item for item in existing if item.source_key}
    legacy_by_word = {item["word"].casefold(): item for item in VOCABULARY}
    for entry in lesson.vocabulary or []:
        key = f"lesson:{lesson.slug}:{entry['slug']}"
        if key in by_source:
            continue
        if any(item.word.casefold() == entry["word"].casefold() for item in existing):
            continue
        legacy = legacy_by_word.get(entry["word"].casefold())
        legacy_key = f"legacy:{legacy['word']}" if legacy else None
        if legacy_key and legacy_key in by_source:
            continue
        matching = next(
            (
                item
                for item in existing
                if item.source_key is None
                and item.word.casefold() == entry["word"].casefold()
            ),
            None,
        )
        if matching is not None:
            matching.source_key = legacy_key or key
            by_source[matching.source_key] = matching
            continue
        item = VocabularyItem(
            user_id=user_id,
            source_key=legacy_key or key,
            word=entry["word"],
            translation=entry["translation"],
        )
        db.add(item)
        by_source[item.source_key] = item
        existing.append(item)


def calculate_schedule(
    rating: ReviewRating,
    *,
    successful_reviews: int,
    failed_reviews: int,
    consecutive_successes: int,
    interval_days: int,
    now: datetime,
) -> ReviewSchedule:
    """Apply the documented Lingvéra schedule; this is not full SM-2."""
    now = as_utc(now)
    if rating is ReviewRating.AGAIN:
        return ReviewSchedule(
            successful_reviews=successful_reviews,
            failed_reviews=failed_reviews + 1,
            consecutive_successes=0,
            interval_days=0,
            next_review_at=now + timedelta(minutes=10),
        )

    next_streak = consecutive_successes + 1
    if rating is ReviewRating.HARD:
        days = (
            1
            if consecutive_successes == 0
            else min(365, max(1, ceil(interval_days * 1.2)))
        )
    elif rating is ReviewRating.GOOD:
        days = (
            2
            if consecutive_successes == 0
            else min(730, max(2, ceil(interval_days * 2)))
        )
    else:  # EASY
        days = (
            4
            if consecutive_successes == 0
            else min(1095, max(4, ceil(interval_days * 2.5)))
        )
    return ReviewSchedule(
        successful_reviews=successful_reviews + 1,
        failed_reviews=failed_reviews,
        consecutive_successes=next_streak,
        interval_days=days,
        next_review_at=now + timedelta(days=days),
    )


def list_due_vocabulary(
    db: Session, user_id: int, *, now: datetime | None = None
) -> list[VocabularyItem]:
    ensure_user_vocabulary(db, user_id)
    due_at = as_utc(now or datetime.now(timezone.utc))
    return list(
        db.scalars(
            select(VocabularyItem)
            .where(
                VocabularyItem.user_id == user_id,
                VocabularyItem.next_review_at <= due_at,
            )
            .order_by(VocabularyItem.next_review_at, VocabularyItem.id)
        )
    )


def reveal_translation(
    db: Session, user_id: int, item_id: int, *, now: datetime
) -> VocabularyItem:
    item = db.scalar(
        select(VocabularyItem)
        .where(VocabularyItem.id == item_id, VocabularyItem.user_id == user_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Vocabulary item not found")
    now = as_utc(now)
    if as_utc(item.next_review_at) > now:
        raise HTTPException(status_code=409, detail="Vocabulary item is not due")
    item.translation_revealed_at = now
    db.commit()
    return item


def submit_vocabulary_review(
    db: Session,
    user_id: int,
    item_id: int,
    rating: ReviewRating,
    *,
    now: datetime,
) -> VocabularyItem:
    item = db.scalar(
        select(VocabularyItem)
        .where(VocabularyItem.id == item_id, VocabularyItem.user_id == user_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Vocabulary item not found")
    now = as_utc(now)
    if as_utc(item.next_review_at) > now:
        raise HTTPException(status_code=409, detail="Vocabulary item is not due")
    if item.translation_revealed_at is None:
        raise HTTPException(
            status_code=409, detail="Reveal the translation before rating"
        )

    previous_due_at = as_utc(item.next_review_at)

    schedule = calculate_schedule(
        rating,
        successful_reviews=item.successful_reviews,
        failed_reviews=item.failed_reviews,
        consecutive_successes=item.consecutive_successes,
        interval_days=item.interval_days,
        now=now,
    )
    item.successful_reviews = schedule.successful_reviews
    item.failed_reviews = schedule.failed_reviews
    item.consecutive_successes = schedule.consecutive_successes
    item.interval_days = schedule.interval_days
    item.last_reviewed_at = now
    item.last_rating = rating.value
    item.next_review_at = schedule.next_review_at
    item.translation_revealed_at = None
    record_learning_activity(
        db,
        user_id,
        "vocabulary_review",
        f"{item_id}:{previous_due_at.isoformat()}",
        now,
    )
    db.commit()
    db.refresh(item)
    return item
