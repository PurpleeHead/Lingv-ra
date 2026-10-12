from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.dependencies import current_user
from app.learning import (
    completed_lessons,
    get_course,
    get_exercise_hint,
    get_lesson as load_lesson,
    get_progress,
    list_course_lessons,
    list_courses,
    submit_answer as grade_answer,
)
from app.models import User, VocabularyItem
from app.schemas import (
    AnswerSubmission,
    DueVocabularyItem,
    SettingsPatch,
    VocabularyReviewResult,
    VocabularyReviewSubmission,
)
from app.vocabulary_review import (
    as_utc,
    ensure_user_vocabulary,
    list_due_vocabulary,
    reveal_translation,
    submit_vocabulary_review,
)
from app.activity import build_dashboard
from datetime import datetime, timezone

app = FastAPI(title="Lingvéra API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(
        dict.fromkeys(
            origin.strip().rstrip("/")
            for origin in [
                settings.mini_app_url,
                *settings.cors_allowed_origins.split(","),
            ]
            if origin.strip()
        )
    ),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-Telegram-Init-Data"],
)


@app.get("/health", tags=["operations"])
def health():
    return {"status": "ok", "service": "lingvera-api"}


@app.get("/ready", tags=["operations"])
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        migrated = inspect(db.get_bind()).has_table("alembic_version")
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    if not migrated:
        raise HTTPException(
            status_code=503, detail="Database migrations have not been applied"
        )
    return {"status": "ready", "database": "ok"}


@app.get("/api/v1/me")
def get_me(user: User = Depends(current_user)):
    return {
        "id": user.id,
        "first_name": user.first_name,
        "settings": {
            "ui_language": user.settings.ui_language,
            "target_language": user.settings.target_language,
            "daily_goal": user.settings.daily_goal,
        },
    }


@app.patch("/api/v1/me/settings")
def patch_settings(
    payload: SettingsPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user.settings, key, value)
    db.commit()
    db.refresh(user)
    return {
        "ui_language": user.settings.ui_language,
        "target_language": user.settings.target_language,
        "daily_goal": user.settings.daily_goal,
    }


@app.get("/api/v1/courses")
def courses(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list_courses(db)


@app.get("/api/v1/courses/{course_slug}")
def course_detail(
    course_slug: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    course = get_course(db, course_slug)
    return {
        "id": course.slug,
        "title": course.title,
        "description": course.description,
        "source_language": course.source_language,
        "target_language": course.target_language,
        "level": course.level,
        "lesson_count": sum(lesson.is_available for lesson in course.lessons),
    }


@app.get("/api/v1/courses/{course_slug}/lessons")
def course_lessons(
    course_slug: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return list_course_lessons(db, user, course_slug)


@app.get("/api/v1/lessons")
def list_lessons(user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Kept as a compatibility endpoint while clients migrate to /courses/{slug}/lessons.
    return list_course_lessons(db, user, "english-a1")


@app.get("/api/v1/lessons/{lesson_slug}")
def lesson_detail(
    lesson_slug: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return load_lesson(db, lesson_slug)


@app.get("/api/v1/lessons/{lesson_slug}/exercises/{exercise_slug}/hints/{level}")
def exercise_hint(
    lesson_slug: str,
    exercise_slug: str,
    level: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return get_exercise_hint(db, user, lesson_slug, exercise_slug, level)


@app.post("/api/v1/lessons/{lesson_slug}/answer")
def submit_answer(
    lesson_slug: str,
    payload: AnswerSubmission,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return grade_answer(db, user, lesson_slug, payload)


@app.get("/api/v1/progress")
def learning_progress(
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return get_progress(db, user)


@app.get("/api/v1/dashboard")
def learning_dashboard(
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return build_dashboard(db, user)


@app.get("/api/v1/progress/lessons")
def progress_lessons(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return completed_lessons(db, user)


@app.get("/api/v1/vocabulary")
def get_vocabulary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ensure_user_vocabulary(db, user.id)
    items = (
        db.query(VocabularyItem)
        .filter(VocabularyItem.user_id == user.id)
        .order_by(VocabularyItem.id)
        .all()
    )
    return [
        {
            "id": i.id,
            "word": i.word,
            "translation": i.translation,
            "next_review_at": as_utc(i.next_review_at).isoformat(),
        }
        for i in items
    ]


@app.get("/api/v1/review/due", response_model=list[DueVocabularyItem])
def due_review(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = list_due_vocabulary(db, user.id)
    return [
        {
            "id": item.id,
            "word": item.word,
            "next_review_at": as_utc(item.next_review_at),
        }
        for item in items
    ]


@app.get("/api/v1/vocabulary/{item_id}/translation")
def reveal_vocabulary_translation(
    item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    item = reveal_translation(db, user.id, item_id, now=datetime.now(timezone.utc))
    return {"id": item.id, "translation": item.translation}


@app.post(
    "/api/v1/vocabulary/{item_id}/review",
    response_model=VocabularyReviewResult,
)
def review_vocabulary_item(
    item_id: int,
    payload: VocabularyReviewSubmission,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    item = submit_vocabulary_review(
        db,
        user.id,
        item_id,
        payload.rating,
        now=datetime.now(timezone.utc),
    )
    return {
        "id": item.id,
        "word": item.word,
        "translation": item.translation,
        "rating": item.last_rating,
        "successful_reviews": item.successful_reviews,
        "failed_reviews": item.failed_reviews,
        "consecutive_successes": item.consecutive_successes,
        "interval_days": item.interval_days,
        "last_reviewed_at": as_utc(item.last_reviewed_at),
        "next_review_at": as_utc(item.next_review_at),
    }
