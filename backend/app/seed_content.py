import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content_schemas import ContentSeed
from app.db import SessionLocal
from app.models import Course, Exercise, Lesson

DEFAULT_CONTENT_FILE = (
    Path(__file__).resolve().parent.parent / "content" / "en_ru_a1.json"
)


def load_content(path: Path = DEFAULT_CONTENT_FILE) -> ContentSeed:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ContentSeed.model_validate(raw)


def seed_content(db: Session, path: Path = DEFAULT_CONTENT_FILE) -> dict[str, int]:
    """Idempotently insert/update bundled authored course content; never delete rows."""
    content = load_content(path)
    course_data = content.course.model_dump()
    course = db.scalar(select(Course).where(Course.slug == content.course.slug))
    if course is None:
        course = Course(**course_data)
        db.add(course)
        db.flush()
    else:
        for key, value in course_data.items():
            setattr(course, key, value)

    lesson_count = 0
    exercise_count = 0
    for lesson_seed in content.lessons:
        lesson_data = lesson_seed.model_dump(exclude={"exercises"})
        lesson_data["vocabulary"] = [
            item.model_dump() for item in lesson_seed.vocabulary
        ]
        lesson = db.scalar(select(Lesson).where(Lesson.slug == lesson_seed.slug))
        if lesson is None:
            lesson = Lesson(course_id=course.id, **lesson_data)
            db.add(lesson)
            db.flush()
        else:
            lesson.course_id = course.id
            for key, value in lesson_data.items():
                setattr(lesson, key, value)
        lesson_count += 1

        for exercise_seed in lesson_seed.exercises:
            exercise_data = {
                "slug": exercise_seed.slug,
                "exercise_type": exercise_seed.type,
                "instruction": exercise_seed.instruction.model_dump(),
                "prompt": exercise_seed.prompt.model_dump(),
                "public_data": exercise_seed.public_data.model_dump(),
                "answer_data": exercise_seed.answer_data.model_dump(),
                "explanation": exercise_seed.explanation.model_dump(),
                "hints": {
                    "level_1": exercise_seed.hints.level_1.model_dump(),
                    "level_2": exercise_seed.hints.level_2.model_dump(),
                },
                "sort_order": exercise_seed.sort_order,
                "is_available": True,
            }
            exercise = db.scalar(
                select(Exercise).where(Exercise.slug == exercise_seed.slug)
            )
            if exercise is None:
                db.add(Exercise(lesson_id=lesson.id, **exercise_data))
            else:
                exercise.lesson_id = lesson.id
                for key, value in exercise_data.items():
                    setattr(exercise, key, value)
            exercise_count += 1
    db.commit()
    return {"courses": 1, "lessons": lesson_count, "exercises": exercise_count}


def main() -> None:
    with SessionLocal() as db:
        counts = seed_content(db)
    print(
        "Seeded Lingvera content (upserted without deleting rows): "
        + ", ".join(f"{key}={value}" for key, value in counts.items())
    )


if __name__ == "__main__":
    main()
