import json
import unicodedata

from fastapi import HTTPException
from sqlalchemy import Integer, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import Course, Exercise, LearningEvent, Lesson, LessonProgress, User
from app.schemas import AnswerSubmission
from app.vocabulary_review import add_lesson_vocabulary
from app.activity import record_learning_activity
from datetime import datetime, timezone


def _localize(value: dict, language: str) -> str:
    return value.get(language) or value.get("ru") or value.get("en") or ""


def _localized(value: dict) -> dict[str, str]:
    fallback = value.get("ru") or value.get("en") or ""
    return {"ru": value.get("ru") or fallback, "en": value.get("en") or fallback}


def _public_exercise(exercise: Exercise) -> dict:
    data = {
        "id": exercise.slug,
        "type": exercise.exercise_type,
        "instruction": _localized(exercise.instruction),
        "prompt": _localized(exercise.prompt),
        "sort_order": exercise.sort_order,
    }
    if exercise.exercise_type == "choice":
        data["choices"] = [
            {"id": choice["id"], "text": _localized(choice["text"])}
            for choice in exercise.public_data["choices"]
        ]
    elif exercise.exercise_type == "text":
        data["placeholder"] = _localized(exercise.public_data["placeholder"])
    elif exercise.exercise_type == "word_order":
        data["tokens"] = exercise.public_data["tokens"]
    else:
        raise HTTPException(status_code=500, detail="Unsupported stored exercise type")
    return data


def list_courses(db: Session) -> list[dict]:
    courses = db.scalars(
        select(Course)
        .where(Course.is_published.is_(True))
        .options(joinedload(Course.lessons))
        .order_by(Course.sort_order, Course.id)
    ).unique()
    return [
        {
            "id": course.slug,
            "title": _localized(course.title),
            "description": _localized(course.description),
            "source_language": course.source_language,
            "target_language": course.target_language,
            "level": course.level,
            "lesson_count": sum(lesson.is_available for lesson in course.lessons),
        }
        for course in courses
    ]


def get_course(db: Session, slug: str) -> Course:
    course = db.scalar(
        select(Course)
        .where(Course.slug == slug, Course.is_published.is_(True))
        .options(joinedload(Course.lessons))
    )
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def list_course_lessons(db: Session, user: User, slug: str) -> list[dict]:
    course = get_course(db, slug)
    completed_ids = set(
        db.scalars(
            select(LessonProgress.lesson_id).where(LessonProgress.user_id == user.id)
        )
    )
    lessons = sorted(
        (lesson for lesson in course.lessons if lesson.is_available),
        key=lambda lesson: (lesson.sort_order, lesson.id),
    )
    next_lesson_id = next(
        (lesson.id for lesson in lessons if lesson.id not in completed_ids), None
    )
    return [
        {
            "id": lesson.slug,
            "title": _localized(lesson.title),
            "description": _localized(lesson.description),
            "sort_order": lesson.sort_order,
            "level": course.level,
            "exercise_count": sum(
                exercise.is_available for exercise in lesson.exercises
            ),
            "available": True,
            "completed": lesson.id in completed_ids,
            "is_next": lesson.id == next_lesson_id,
        }
        for lesson in lessons
    ]


def get_lesson(db: Session, slug: str) -> dict:
    lesson = db.scalar(
        select(Lesson)
        .join(Course)
        .where(
            Lesson.slug == slug,
            Lesson.is_available.is_(True),
            Course.is_published.is_(True),
        )
        .options(joinedload(Lesson.exercises), joinedload(Lesson.course))
    )
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lesson not found")
    exercises = sorted(
        (exercise for exercise in lesson.exercises if exercise.is_available),
        key=lambda exercise: (exercise.sort_order, exercise.id),
    )
    return {
        "id": lesson.slug,
        "course_id": lesson.course.slug,
        "title": _localized(lesson.title),
        "description": _localized(lesson.description),
        "vocabulary": lesson.vocabulary or [],
        "level": lesson.course.level,
        "sort_order": lesson.sort_order,
        "exercises": [_public_exercise(exercise) for exercise in exercises],
    }


def get_exercise_hint(
    db: Session, user: User, lesson_slug: str, exercise_slug: str, level: int
) -> dict:
    if level not in (1, 2):
        raise HTTPException(status_code=422, detail="Hint level must be 1 or 2")
    exercise = db.scalar(
        select(Exercise)
        .join(Lesson)
        .join(Course)
        .where(
            Lesson.slug == lesson_slug,
            Exercise.slug == exercise_slug,
            Lesson.is_available.is_(True),
            Exercise.is_available.is_(True),
            Course.is_published.is_(True),
        )
    )
    if exercise is None:
        raise HTTPException(status_code=404, detail="Exercise not found or unavailable")
    hints = getattr(exercise, "hints", None)
    hint = hints.get(f"level_{level}") if isinstance(hints, dict) else None
    if not isinstance(hint, dict) or not any(
        isinstance(hint.get(language), str) and hint[language].strip()
        for language in ("ru", "en")
    ):
        raise HTTPException(status_code=404, detail="Hint not available")
    return {
        "exercise_id": exercise.slug,
        "level": level,
        "hint": _localize(hint, user.settings.ui_language),
    }


def normalize_text(value: str) -> str:
    # Preserve accents and word boundaries; only normalize Unicode composition,
    # case and runs of whitespace.
    return unicodedata.normalize("NFC", " ".join(value.split())).casefold()


def _grade(
    exercise: Exercise, answer: str | list[str], language: str
) -> tuple[bool, str]:
    if exercise.exercise_type == "choice":
        if not isinstance(answer, str):
            raise HTTPException(
                status_code=422, detail="Choice answer must be an option ID"
            )
        options = {item["id"]: item for item in exercise.public_data["choices"]}
        if answer not in options:
            raise HTTPException(
                status_code=422, detail="Answer is not an available option"
            )
        correct_id = exercise.answer_data["correct"]
        return answer == correct_id, _localize(options[correct_id]["text"], language)

    if exercise.exercise_type == "text":
        if not isinstance(answer, str):
            raise HTTPException(status_code=422, detail="Text answer must be a string")
        accepted = exercise.answer_data["accepted"]
        return any(
            normalize_text(answer) == normalize_text(value) for value in accepted
        ), accepted[0]

    if exercise.exercise_type == "word_order":
        if not isinstance(answer, list) or any(
            not isinstance(value, str) for value in answer
        ):
            raise HTTPException(
                status_code=422, detail="Word order answer must be a list of token IDs"
            )
        expected = exercise.answer_data["order"]
        if len(answer) != len(set(answer)) or set(answer) != set(expected):
            raise HTTPException(
                status_code=422,
                detail="Answer must use each available token exactly once",
            )
        tokens = {
            token["id"]: token["text"] for token in exercise.public_data["tokens"]
        }
        correct_answer = " ".join(tokens[token_id] for token_id in expected)
        return answer == expected, correct_answer

    raise HTTPException(status_code=500, detail="Unsupported stored exercise type")


def submit_answer(
    db: Session, user: User, lesson_slug: str, payload: AnswerSubmission
) -> dict:
    exercise = db.scalar(
        select(Exercise)
        .join(Lesson)
        .join(Course)
        .where(
            Lesson.slug == lesson_slug,
            Exercise.slug == payload.exercise_id,
            Lesson.is_available.is_(True),
            Exercise.is_available.is_(True),
            Course.is_published.is_(True),
        )
    )
    if exercise is None:
        raise HTTPException(status_code=404, detail="Exercise not found or unavailable")

    language = user.settings.ui_language
    correct, correct_answer = _grade(exercise, payload.answer, language)
    stored_answer = (
        payload.answer
        if isinstance(payload.answer, str)
        else json.dumps(payload.answer, ensure_ascii=False)
    )
    db.add(
        LearningEvent(
            user_id=user.id,
            lesson_id=lesson_slug,
            exercise_id=exercise.slug,
            answer=stored_answer,
            is_correct=correct,
        )
    )
    db.flush()
    if correct:
        record_learning_activity(
            db,
            user.id,
            "exercise",
            f"{lesson_slug}:{exercise.slug}",
            datetime.now(timezone.utc),
        )

    lesson = db.scalar(
        select(Lesson)
        .where(Lesson.id == exercise.lesson_id)
        .options(joinedload(Lesson.exercises))
    )
    available_ids = {item.slug for item in lesson.exercises if item.is_available}
    successful_ids = set(
        db.scalars(
            select(LearningEvent.exercise_id)
            .where(
                LearningEvent.user_id == user.id,
                LearningEvent.lesson_id == lesson_slug,
                LearningEvent.is_correct.is_(True),
            )
            .distinct()
        )
    )
    lesson_completed = bool(available_ids) and available_ids.issubset(successful_ids)
    if lesson_completed:
        existing = db.scalar(
            select(LessonProgress.id).where(
                LessonProgress.user_id == user.id,
                LessonProgress.lesson_id == lesson.id,
            )
        )
        if existing is None:
            try:
                with db.begin_nested():
                    db.add(LessonProgress(user_id=user.id, lesson_id=lesson.id))
                    db.flush()
            except IntegrityError:
                # Concurrent retries may race on the unique completion key.
                pass
        add_lesson_vocabulary(db, user.id, lesson)
    db.commit()
    return {
        "correct": correct,
        "correct_answer": correct_answer,
        "explanation": _localize(exercise.explanation, language),
        "lesson_completed": lesson_completed,
    }


def get_progress(db: Session, user: User) -> dict:
    aggregate = db.execute(
        select(
            LearningEvent.lesson_id,
            func.count(LearningEvent.id),
            func.sum(LearningEvent.is_correct.cast(Integer)),
        )
        .where(LearningEvent.user_id == user.id)
        .group_by(LearningEvent.lesson_id)
    ).all()
    stats = {
        slug: {
            "attempts": attempts,
            "correct": correct or 0,
            "incorrect": attempts - (correct or 0),
        }
        for slug, attempts, correct in aggregate
    }
    completed = set(
        db.scalars(
            select(Lesson.slug)
            .join(LessonProgress, LessonProgress.lesson_id == Lesson.id)
            .where(LessonProgress.user_id == user.id)
        )
    )
    last_activity = db.scalar(
        select(func.max(LearningEvent.created_at)).where(
            LearningEvent.user_id == user.id
        )
    )
    return {
        "attempts": sum(item["attempts"] for item in stats.values()),
        "correct_answers": sum(item["correct"] for item in stats.values()),
        "incorrect_answers": sum(item["incorrect"] for item in stats.values()),
        "last_activity_at": last_activity.isoformat() if last_activity else None,
        "lessons": [
            {"lesson_id": slug, **values, "completed": slug in completed}
            for slug, values in sorted(stats.items())
        ],
    }


def completed_lessons(db: Session, user: User) -> list[dict]:
    rows = db.execute(
        select(Lesson.slug, Lesson.title, LessonProgress.completed_at)
        .join(LessonProgress, LessonProgress.lesson_id == Lesson.id)
        .where(LessonProgress.user_id == user.id)
        .order_by(LessonProgress.completed_at.desc(), Lesson.id)
    ).all()
    return [
        {
            "lesson_id": slug,
            "title": _localize(title, user.settings.ui_language),
            "completed_at": completed_at.isoformat(),
        }
        for slug, title, completed_at in rows
    ]
