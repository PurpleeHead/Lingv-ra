import unittest
import json
from types import SimpleNamespace

from pydantic import ValidationError

from app.content_schemas import ContentSeed
from app.content_quality import validate_content_quality
from app.seed_content import DEFAULT_CONTENT_FILE, load_content
from app.learning import _grade


class ContentTests(unittest.TestCase):
    def test_local_course_is_valid_and_covers_all_exercise_types(self):
        content = load_content()
        validate_content_quality(content)
        self.assertEqual(content.course.source_language, "ru")
        self.assertEqual(content.course.target_language, "en")
        exercise_types = {
            exercise.type for lesson in content.lessons for exercise in lesson.exercises
        }
        self.assertEqual(exercise_types, {"choice", "text", "word_order"})
        self.assertEqual(len(content.lessons), 30)
        self.assertEqual(sum(len(lesson.exercises) for lesson in content.lessons), 120)
        self.assertTrue(
            all(4 <= len(lesson.exercises) <= 6 for lesson in content.lessons)
        )
        self.assertTrue(all(lesson.vocabulary for lesson in content.lessons))
        self.assertTrue(
            all(
                exercise.hints.level_1.ru.strip()
                and exercise.hints.level_1.en.strip()
                and exercise.hints.level_2.ru.strip()
                and exercise.hints.level_2.en.strip()
                for lesson in content.lessons
                for exercise in lesson.exercises
            )
        )
        self.assertEqual(
            [lesson.sort_order for lesson in content.lessons], list(range(1, 31))
        )
        self.assertEqual(
            [lesson.slug for lesson in content.lessons[:15]],
            [
                "hello-basics",
                "about-me",
                "daily-routine",
                "numbers-age",
                "countries",
                "family",
                "everyday-objects",
                "describing-people",
                "present-simple",
                "questions-negatives",
                "telling-time",
                "food-drinks",
                "at-the-cafe",
                "town-directions",
                "a1-review",
            ],
        )
        baseline_exercise_ids = {
            "hello-1",
            "hello-2",
            "about-1",
            "about-2",
            "routine-1",
            "routine-2",
            "numbers-1",
            "numbers-2",
            "numbers-3",
            "countries-1",
            "countries-2",
            "countries-3",
            "family-1",
            "family-2",
            "family-3",
            "objects-1",
            "objects-2",
            "objects-3",
            "describe-1",
            "describe-2",
            "describe-3",
            "present-1",
            "present-2",
            "present-3",
            "questions-1",
            "questions-2",
            "questions-3",
            "time-1",
            "time-2",
            "time-3",
            "food-1",
            "food-2",
            "food-3",
            "cafe-1",
            "cafe-2",
            "cafe-3",
            "town-1",
            "town-2",
            "town-3",
            "review-1",
            "review-2",
            "review-3",
        }
        self.assertTrue(
            baseline_exercise_ids.issubset(
                {
                    exercise.slug
                    for lesson in content.lessons
                    for exercise in lesson.exercises
                }
            )
        )

    def test_invalid_exercise_answer_structure_is_rejected(self):
        source = json.loads(DEFAULT_CONTENT_FILE.read_text(encoding="utf-8"))
        source["lessons"][1]["exercises"][1]["answer_data"]["order"] = [
            "t1",
            "unknown-token",
        ]
        with self.assertRaises(ValidationError):
            ContentSeed.model_validate(source)

    def test_validator_rejects_duplicate_course_ids_blank_translations_and_prompts(
        self,
    ):
        for mutate in (
            lambda data: data["lessons"][1]["exercises"][0].update(
                slug=data["lessons"][0]["exercises"][0]["slug"]
            ),
            lambda data: data["lessons"][0]["title"].update(ru="   "),
            lambda data: data["lessons"][0]["exercises"][2].update(
                prompt=data["lessons"][0]["exercises"][0]["prompt"]
            ),
        ):
            source = json.loads(DEFAULT_CONTENT_FILE.read_text(encoding="utf-8"))
            mutate(source)
            with self.subTest(mutate=mutate), self.assertRaises(ValidationError):
                ContentSeed.model_validate(source)

    def test_choice_labels_must_not_make_the_answer_ambiguous(self):
        source = json.loads(DEFAULT_CONTENT_FILE.read_text(encoding="utf-8"))
        exercise = source["lessons"][0]["exercises"][0]
        exercise["public_data"]["choices"][1]["text"] = exercise["public_data"][
            "choices"
        ][0]["text"]
        with self.assertRaises(ValidationError):
            ContentSeed.model_validate(source)

    def test_every_authored_answer_key_is_accepted_and_a_clear_wrong_answer_is_rejected(
        self,
    ):
        content = load_content()
        checked = 0
        for lesson in content.lessons:
            for authored in lesson.exercises:
                exercise = SimpleNamespace(
                    exercise_type=authored.type,
                    public_data=authored.public_data.model_dump(),
                    answer_data=authored.answer_data.model_dump(),
                )
                if authored.type == "choice":
                    correct = authored.answer_data.correct
                    options = [item.id for item in authored.public_data.choices]
                    self.assertTrue(_grade(exercise, correct, "ru")[0], authored.slug)
                    wrong = next(option for option in options if option != correct)
                    self.assertFalse(_grade(exercise, wrong, "ru")[0], authored.slug)
                elif authored.type == "text":
                    for accepted in authored.answer_data.accepted:
                        self.assertTrue(
                            _grade(exercise, accepted, "ru")[0], authored.slug
                        )
                    self.assertFalse(
                        _grade(exercise, "not an accepted answer", "ru")[0],
                        authored.slug,
                    )
                else:
                    correct_order = authored.answer_data.order
                    self.assertNotEqual(
                        [token.id for token in authored.public_data.tokens],
                        correct_order,
                        authored.slug,
                    )
                    self.assertTrue(
                        _grade(exercise, correct_order, "ru")[0], authored.slug
                    )
                    wrong_order = correct_order[1:] + correct_order[:1]
                    self.assertFalse(
                        _grade(exercise, wrong_order, "ru")[0], authored.slug
                    )
                checked += 1
        self.assertEqual(checked, 120)


if __name__ == "__main__":
    unittest.main()
