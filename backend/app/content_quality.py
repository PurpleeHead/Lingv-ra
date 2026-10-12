"""Deterministic checks for authored A1 content and seeded DB records."""

from collections import Counter
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content_schemas import ContentSeed
from app.models import Course, Exercise, Lesson


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", " ".join(value.split())).casefold()


def validate_content_quality(content: ContentSeed) -> None:
    """Check invariants that are meaningful beyond Pydantic field shapes.

    This is mechanical validation. It cannot certify grammar, idiom, or teaching quality.
    """
    lesson_slugs = [lesson.slug for lesson in content.lessons]
    exercise_slugs = [
        exercise.slug for lesson in content.lessons for exercise in lesson.exercises
    ]
    if len(lesson_slugs) != len(set(lesson_slugs)):
        raise ValueError("duplicate lesson slugs")
    if len(exercise_slugs) != len(set(exercise_slugs)):
        raise ValueError("duplicate exercise slugs")

    fingerprints: list[tuple[str, str, str]] = []
    hint_text: dict[int, list[str]] = {1: [], 2: []}
    hint_count = 0
    for lesson in content.lessons:
        vocabulary_slugs = [item.slug for item in lesson.vocabulary]
        if len(vocabulary_slugs) != len(set(vocabulary_slugs)):
            raise ValueError(f"lesson {lesson.slug} has duplicate vocabulary keys")
        for exercise in lesson.exercises:
            if re.search(r"[А-Яа-яЁё]", exercise.instruction.en):
                raise ValueError(
                    f"exercise {exercise.slug} has Russian text in its English instruction"
                )
            fingerprints.append(
                (
                    exercise.type,
                    _normalise(exercise.prompt.ru),
                    _normalise(exercise.prompt.en),
                )
            )
            hint_count += 1
            for level in (1, 2):
                hint = getattr(exercise.hints, f"level_{level}")
                hint_text[level].extend((_normalise(hint.ru), _normalise(hint.en)))

            hints = " ".join(
                (
                    exercise.hints.level_1.ru,
                    exercise.hints.level_1.en,
                    exercise.hints.level_2.ru,
                    exercise.hints.level_2.en,
                )
            )
            normalised_hints = _normalise(hints)
            if exercise.type == "choice":
                options = {item.id: item for item in exercise.public_data.choices}
                answer = options[exercise.answer_data.correct]
                for label in (answer.text.ru, answer.text.en):
                    label = _normalise(label)
                    if len(label) >= 5 and label in normalised_hints:
                        raise ValueError(
                            f"exercise {exercise.slug} hint gives away its correct option"
                        )
            elif exercise.type == "text":
                for answer in exercise.answer_data.accepted:
                    answer = _normalise(answer)
                    if len(answer) >= 10 and answer in normalised_hints:
                        raise ValueError(
                            f"exercise {exercise.slug} hint gives away its complete text answer"
                        )
            else:
                tokens = {token.id: token.text for token in exercise.public_data.tokens}
                expected = " ".join(
                    tokens[token_id] for token_id in exercise.answer_data.order
                )
                public_order = [token.id for token in exercise.public_data.tokens]
                if public_order == exercise.answer_data.order:
                    raise ValueError(
                        f"exercise {exercise.slug} exposes its correct token order"
                    )
                if (
                    len(_normalise(expected)) >= 12
                    and _normalise(expected) in normalised_hints
                ):
                    raise ValueError(
                        f"exercise {exercise.slug} hint gives away its complete word-order answer"
                    )

    duplicates = [
        fingerprint for fingerprint, count in Counter(fingerprints).items() if count > 1
    ]
    if duplicates:
        raise ValueError(f"duplicate exercise prompts found: {duplicates[:5]}")
    if hint_count != len(exercise_slugs):
        raise ValueError("every exercise must have exactly two hint levels")
    for level, values in hint_text.items():
        if max(Counter(values).values(), default=0) > 5:
            raise ValueError(f"level {level} reuses a generic hint too widely")


def validate_seeded_records(db: Session, content: ContentSeed) -> None:
    """Raise a useful error when an authored course is missing or mis-seeded."""
    course = db.scalar(select(Course).where(Course.slug == content.course.slug))
    if course is None:
        raise ValueError(f"seeded course is missing: {content.course.slug}")
    expected_course = content.course.model_dump()
    if any(getattr(course, key) != value for key, value in expected_course.items()):
        raise ValueError(f"seeded course content is out of sync: {content.course.slug}")
    for lesson_seed in content.lessons:
        lesson = db.scalar(select(Lesson).where(Lesson.slug == lesson_seed.slug))
        if lesson is None or lesson.course_id != course.id:
            raise ValueError(
                f"lesson is missing or linked to the wrong course: {lesson_seed.slug}"
            )
        expected_lesson = lesson_seed.model_dump(exclude={"exercises"})
        expected_lesson["vocabulary"] = [
            item.model_dump() for item in lesson_seed.vocabulary
        ]
        if any(getattr(lesson, key) != value for key, value in expected_lesson.items()):
            raise ValueError(
                f"seeded lesson content is out of sync: {lesson_seed.slug}"
            )
        for exercise_seed in lesson_seed.exercises:
            exercise = db.scalar(
                select(Exercise).where(Exercise.slug == exercise_seed.slug)
            )
            if exercise is None or exercise.lesson_id != lesson.id:
                raise ValueError(
                    f"exercise is missing or linked to the wrong lesson: {exercise_seed.slug}"
                )
            if (
                exercise.sort_order != exercise_seed.sort_order
                or exercise.exercise_type != exercise_seed.type
                or exercise.instruction != exercise_seed.instruction.model_dump()
                or exercise.prompt != exercise_seed.prompt.model_dump()
                or exercise.public_data != exercise_seed.public_data.model_dump()
                or exercise.answer_data != exercise_seed.answer_data.model_dump()
                or exercise.explanation != exercise_seed.explanation.model_dump()
                or exercise.hints
                != {
                    "level_1": exercise_seed.hints.level_1.model_dump(),
                    "level_2": exercise_seed.hints.level_2.model_dump(),
                }
            ):
                raise ValueError(
                    f"seeded exercise content is out of sync: {exercise_seed.slug}"
                )


def content_counts(content: ContentSeed) -> dict[str, object]:
    return {
        "courses": 1,
        "lessons": len(content.lessons),
        "exercises": sum(len(lesson.exercises) for lesson in content.lessons),
        "exercise_types": sorted(
            {
                exercise.type
                for lesson in content.lessons
                for exercise in lesson.exercises
            }
        ),
    }
