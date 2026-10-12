import hashlib
import hmac
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import urlencode

from fastapi.testclient import TestClient
from sqlalchemy import Column, MetaData, String, Table, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, settings
from app.db import Base, create_database_engine, get_db
from app.main import app
from app.models import LearningActivity, LearningEvent, User, VocabularyItem
from app.models import Course, Exercise, LessonProgress
from app.content_quality import validate_content_quality
from app.seed_content import load_content, seed_content


def signed_data(token: str, user_id: int, auth_date: int | None = None) -> str:
    import time

    fields = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "user": json.dumps(
            {"id": user_id, "first_name": "Тест"},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_database_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.factory() as session:
            seed_content(session)

        def override_db():
            with self.factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        self.telegram_settings = Settings(
            app_env="test", auth_mode="telegram", telegram_bot_token="fixture-token"
        )
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_bundled_content_passes_content_quality_checks(self):
        content = load_content()
        validate_content_quality(content)

        exercises = {
            exercise.slug: exercise
            for lesson in content.lessons
            for exercise in lesson.exercises
        }
        self.assertEqual(
            exercises["numbers-1"].prompt.en,
            "How do you say “five” in English?",
        )
        self.assertEqual(
            exercises["family-1"].prompt.en,
            "What does “brother” mean?",
        )
        self.assertEqual(
            exercises["review-1"].prompt.en,
            "Choose the grammatically correct sentence.",
        )

    def test_cors_allows_configured_frontend_origin(self):
        origin = settings.mini_app_url.rstrip("/")
        response = self.client.options(
            "/api/v1/me",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), origin)

        denied = self.client.get("/health", headers={"Origin": "http://untrusted.invalid"})
        self.assertNotEqual(
            denied.headers.get("access-control-allow-origin"),
            "http://untrusted.invalid",
        )

    def test_private_route_requires_verified_initdata(self):
        with patch("app.dependencies.settings", self.telegram_settings):
            self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
            self.assertEqual(
                self.client.get("/api/v1/lessons/hello-basics").status_code, 401
            )
            response = self.client.get(
                "/api/v1/me",
                headers={"X-Telegram-Init-Data": signed_data("fixture-token", 1234)},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["settings"]["ui_language"], "ru")
        self.assertEqual(response.json()["settings"]["target_language"], "en")

    def test_hints_are_authenticated_localized_and_not_in_lesson_payload(self):
        headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 98761)}
        with patch("app.dependencies.settings", self.telegram_settings):
            unauthorized = self.client.get(
                "/api/v1/lessons/hello-basics/exercises/hello-1/hints/1"
            )
            lesson = self.client.get("/api/v1/lessons/hello-basics", headers=headers)
            first_hint = self.client.get(
                "/api/v1/lessons/hello-basics/exercises/hello-1/hints/1",
                headers=headers,
            )
            second_hint = self.client.get(
                "/api/v1/lessons/hello-basics/exercises/hello-1/hints/2",
                headers=headers,
            )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertNotIn("hints", lesson.json()["exercises"][0])
        self.assertEqual(first_hint.status_code, 200)
        self.assertEqual(first_hint.json()["level"], 1)
        self.assertEqual(set(first_hint.json()), {"exercise_id", "level", "hint"})
        self.assertEqual(second_hint.status_code, 200)
        self.assertNotIn("Hello", second_hint.json()["hint"])
        with patch("app.dependencies.settings", self.telegram_settings):
            changed_language = self.client.patch(
                "/api/v1/me/settings",
                headers=headers,
                json={"ui_language": "en"},
            )
            english_hint = self.client.get(
                "/api/v1/lessons/hello-basics/exercises/hello-1/hints/1",
                headers=headers,
            )
        self.assertEqual(changed_language.status_code, 200)
        self.assertIn("greeting", english_hint.json()["hint"])

    def test_reported_routine_hint_request_succeeds(self):
        headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 98763)}
        with patch("app.dependencies.settings", self.telegram_settings):
            response = self.client.get(
                "/api/v1/lessons/daily-routine/exercises/routine-1/hints/1",
                headers=headers,
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["exercise_id"], "routine-1")
        self.assertEqual(response.json()["level"], 1)

    def test_unknown_hint_resources_and_missing_hint_are_safe(self):
        headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 98764)}
        with patch("app.dependencies.settings", self.telegram_settings):
            unknown_lesson = self.client.get(
                "/api/v1/lessons/no-such-lesson/exercises/routine-1/hints/1",
                headers=headers,
            )
            unknown_exercise = self.client.get(
                "/api/v1/lessons/daily-routine/exercises/no-such-exercise/hints/1",
                headers=headers,
            )
            with self.factory() as db:
                exercise = db.scalar(
                    select(Exercise).where(Exercise.slug == "routine-1")
                )
                original_hints = exercise.hints
                exercise.hints = None
                db.commit()
            missing_hint = self.client.get(
                "/api/v1/lessons/daily-routine/exercises/routine-1/hints/1",
                headers=headers,
            )
            with self.factory() as db:
                exercise = db.scalar(
                    select(Exercise).where(Exercise.slug == "routine-1")
                )
                exercise.hints = original_hints
                db.commit()
        self.assertEqual(unknown_lesson.status_code, 404)
        self.assertEqual(unknown_exercise.status_code, 404)
        self.assertEqual(missing_hint.status_code, 404)
        self.assertEqual(missing_hint.json()["detail"], "Hint not available")

    def test_hint_requests_do_not_change_learning_data_or_dashboard(self):
        headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 98765)}
        with patch("app.dependencies.settings", self.telegram_settings):
            user = self.client.get("/api/v1/me", headers=headers).json()
            user_id = user["id"]
            before_dashboard = self.client.get(
                "/api/v1/dashboard", headers=headers
            ).json()
            with self.factory() as db:
                before = {
                    model.__tablename__: db.scalar(
                        select(func.count())
                        .select_from(model)
                        .where(model.user_id == user_id)
                    )
                    for model in (
                        LearningEvent,
                        LearningActivity,
                        LessonProgress,
                        VocabularyItem,
                    )
                }
            for level in (1, 2):
                response = self.client.get(
                    f"/api/v1/lessons/daily-routine/exercises/routine-1/hints/{level}",
                    headers=headers,
                )
                self.assertEqual(response.status_code, 200)
            after_dashboard = self.client.get(
                "/api/v1/dashboard", headers=headers
            ).json()
            with self.factory() as db:
                after = {
                    model.__tablename__: db.scalar(
                        select(func.count())
                        .select_from(model)
                        .where(model.user_id == user_id)
                    )
                    for model in (
                        LearningEvent,
                        LearningActivity,
                        LessonProgress,
                        VocabularyItem,
                    )
                }
        self.assertEqual(before, after)
        self.assertEqual(before_dashboard, after_dashboard)
        with patch("app.dependencies.settings", self.telegram_settings):
            wrong = self.client.post(
                "/api/v1/lessons/daily-routine/answer",
                headers=headers,
                json={"exercise_id": "routine-1", "answer": "I wake at 7"},
            )
            correct = self.client.post(
                "/api/v1/lessons/daily-routine/answer",
                headers=headers,
                json={"exercise_id": "routine-1", "answer": "I get up at seven"},
            )
        self.assertEqual(wrong.status_code, 200)
        self.assertFalse(wrong.json()["correct"])
        self.assertEqual(correct.status_code, 200)
        self.assertTrue(correct.json()["correct"])

    def test_hint_level_and_exercise_scope_are_validated(self):
        headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 98762)}
        with patch("app.dependencies.settings", self.telegram_settings):
            bad_level = self.client.get(
                "/api/v1/lessons/hello-basics/exercises/hello-1/hints/3",
                headers=headers,
            )
            wrong_lesson = self.client.get(
                "/api/v1/lessons/about-me/exercises/hello-1/hints/1",
                headers=headers,
            )
        self.assertEqual(bad_level.status_code, 422)
        self.assertEqual(wrong_lesson.status_code, 404)

    def test_settings_updates_are_scoped_to_authenticated_user(self):
        first_headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 12341)}
        second_headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 12342)}
        with patch("app.dependencies.settings", self.telegram_settings):
            updated = self.client.patch(
                "/api/v1/me/settings",
                headers=first_headers,
                json={"daily_goal": 25},
            )
            other_user = self.client.get("/api/v1/me", headers=second_headers)
            unauthorized_update = self.client.patch(
                "/api/v1/me/settings", json={"daily_goal": 30}
            )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["daily_goal"], 25)
        self.assertEqual(other_user.json()["settings"]["daily_goal"], 10)
        self.assertEqual(unauthorized_update.status_code, 401)

    def test_liveness_and_database_readiness(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/ready").status_code, 503)
        Table(
            "alembic_version",
            MetaData(),
            Column("version_num", String(32), primary_key=True),
        ).create(self.engine)
        self.assertEqual(self.client.get("/ready").status_code, 200)

    def test_changed_initdata_does_not_create_user(self):
        signed = signed_data("fixture-token", 1234) + "&user=%7B%22id%22%3A9999%7D"
        with patch("app.dependencies.settings", self.telegram_settings):
            response = self.client.get(
                "/api/v1/me", headers={"X-Telegram-Init-Data": signed}
            )
        self.assertEqual(response.status_code, 401)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(User)), None)

    def test_dev_identity_cannot_be_configured_for_production(self):
        with self.assertRaises(ValueError):
            Settings(app_env="production", auth_mode="dev")
        with self.assertRaises(ValueError):
            Settings(
                app_env="production",
                auth_mode="telegram",
                mini_app_url="https://mini.example",
            )
        with self.assertRaises(ValueError):
            Settings(
                app_env="production",
                auth_mode="telegram",
                telegram_bot_token="fixture-token",
                mini_app_url="http://mini.example",
            )

    def test_settings_reject_null_and_unsupported_locale(self):
        with patch("app.dependencies.settings", self.telegram_settings):
            headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 1234)}
            self.client.get("/api/v1/me", headers=headers)
            null_response = self.client.patch(
                "/api/v1/me/settings", headers=headers, json={"daily_goal": None}
            )
            locale_response = self.client.patch(
                "/api/v1/me/settings", headers=headers, json={"ui_language": "vi"}
            )
        self.assertEqual(null_response.status_code, 422)
        self.assertEqual(locale_response.status_code, 422)

    def test_dashboard_zero_state_and_user_scoped_verified_activity(self):
        first_headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 7001)}
        second_headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 7002)}
        with patch("app.dependencies.settings", self.telegram_settings):
            empty = self.client.get("/api/v1/dashboard", headers=first_headers).json()
            wrong = self.client.post(
                "/api/v1/lessons/hello-basics/answer",
                headers=first_headers,
                json={"exercise_id": "hello-1", "answer": "goodbye"},
            )
            self.client.post(
                "/api/v1/lessons/hello-basics/answer",
                headers=first_headers,
                json={"exercise_id": "hello-1", "answer": "hello"},
            )
            self.client.post(
                "/api/v1/lessons/hello-basics/answer",
                headers=first_headers,
                json={"exercise_id": "hello-1", "answer": "hello"},
            )
            owner = self.client.get("/api/v1/dashboard", headers=first_headers).json()
            other = self.client.get("/api/v1/dashboard", headers=second_headers).json()
            unauthorized = self.client.get("/api/v1/dashboard")
        self.assertEqual(empty["today"]["total_actions"], 0)
        self.assertEqual(empty["current_streak_days"], 0)
        self.assertEqual(len(empty["recent_activity"]), 7)
        self.assertFalse(wrong.json()["correct"])
        self.assertEqual(owner["today"]["exercise_actions"], 1)
        self.assertEqual(owner["stats"]["exercises_attempted"], 3)
        self.assertEqual(owner["stats"]["correct_answer_submissions"], 2)
        self.assertEqual(owner["stats"]["unique_exercises_answered_correctly"], 1)
        self.assertEqual(other["today"]["total_actions"], 0)
        self.assertEqual(unauthorized.status_code, 401)

    def test_dashboard_daily_goal_is_persisted_and_validated(self):
        headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 7003)}
        with patch("app.dependencies.settings", self.telegram_settings):
            update = self.client.patch(
                "/api/v1/me/settings", headers=headers, json={"daily_goal": 15}
            )
            dashboard = self.client.get("/api/v1/dashboard", headers=headers)
            invalid = self.client.patch(
                "/api/v1/me/settings", headers=headers, json={"daily_goal": 4}
            )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(dashboard.json()["today"]["goal"], 15)
        self.assertEqual(invalid.status_code, 422)

    def test_answer_is_saved_and_user_scoped(self):
        settings = Settings(
            app_env="test", auth_mode="telegram", telegram_bot_token="fixture-token"
        )
        with patch("app.dependencies.settings", settings):
            first = self.client.post(
                "/api/v1/lessons/hello-basics/answer",
                headers={"X-Telegram-Init-Data": signed_data("fixture-token", 111)},
                json={"exercise_id": "hello-1", "answer": "hello"},
            )
            second = self.client.post(
                "/api/v1/lessons/hello-basics/answer",
                headers={"X-Telegram-Init-Data": signed_data("fixture-token", 222)},
                json={"exercise_id": "hello-1", "answer": "goodbye"},
            )
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["correct"])
        self.assertFalse(second.json()["correct"])
        with self.factory() as db:
            events = db.scalars(select(LearningEvent)).all()
            self.assertEqual(len(events), 2)
            self.assertNotEqual(events[0].user_id, events[1].user_id)

    def test_courses_lessons_and_exercises_hide_answers(self):
        headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 4001)}
        with patch("app.dependencies.settings", self.telegram_settings):
            courses = self.client.get("/api/v1/courses", headers=headers)
            course = self.client.get("/api/v1/courses/english-a1", headers=headers)
            lessons = self.client.get(
                "/api/v1/courses/english-a1/lessons", headers=headers
            )
            lesson = self.client.get("/api/v1/lessons/about-me", headers=headers)
        self.assertEqual(courses.status_code, 200)
        self.assertEqual(courses.json()[0]["target_language"], "en")
        self.assertEqual(course.json()["title"]["ru"], "Английский с нуля")
        self.assertEqual(
            [item["id"] for item in lessons.json()[:15]],
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
        self.assertTrue(lessons.json()[0]["is_next"])
        self.assertEqual(sum(item["is_next"] for item in lessons.json()), 1)
        self.assertTrue(all(item["available"] for item in lessons.json()))
        self.assertEqual(len(lessons.json()), 30)
        body = lesson.json()
        self.assertEqual(len(body["vocabulary"]), 4)
        self.assertEqual(body["exercises"][1]["type"], "word_order")
        self.assertNotEqual(
            [token["id"] for token in body["exercises"][1]["tokens"]],
            ["t1", "t2", "t3", "t4"],
        )
        self.assertTrue(
            all(
                "answer_data" not in exercise
                and "correct_answer" not in exercise
                and "explanation" not in exercise
                for exercise in body["exercises"]
            )
        )

    def test_learning_journey_persists_across_reopened_api_requests(self):
        headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 4110)}
        with patch("app.dependencies.settings", self.telegram_settings):
            course_list = self.client.get("/api/v1/courses", headers=headers)
            lesson_list = self.client.get(
                "/api/v1/courses/english-a1/lessons", headers=headers
            )
            lesson = self.client.get("/api/v1/lessons/hello-basics", headers=headers)
            exercise_payload = lesson.json()["exercises"][0]
            self.assertNotIn("answer_data", exercise_payload)
            self.assertNotIn("correct_answer", exercise_payload)
            result = self.client.post(
                "/api/v1/lessons/hello-basics/answer",
                headers=headers,
                json={"exercise_id": exercise_payload["id"], "answer": "hello"},
            )
            second_result = self.client.post(
                "/api/v1/lessons/hello-basics/answer",
                headers=headers,
                json={"exercise_id": "hello-2", "answer": "Nice to meet you"},
            )
            self.client.post(
                "/api/v1/lessons/hello-basics/answer",
                headers=headers,
                json={"exercise_id": "hello-3", "answer": "fine"},
            )
            final_result = self.client.post(
                "/api/v1/lessons/hello-basics/answer",
                headers=headers,
                json={"exercise_id": "hello-4", "answer": "My name is Lena"},
            )
            progress = self.client.get("/api/v1/progress", headers=headers)
            reopened_profile = self.client.get("/api/v1/me", headers=headers)
            reopened_progress = self.client.get("/api/v1/progress", headers=headers)
            reopened_lessons = self.client.get(
                "/api/v1/courses/english-a1/lessons", headers=headers
            )
        self.assertEqual(course_list.status_code, 200)
        self.assertEqual(lesson_list.status_code, 200)
        self.assertTrue(result.json()["correct"])
        self.assertFalse(second_result.json()["lesson_completed"])
        self.assertTrue(final_result.json()["lesson_completed"])
        self.assertEqual(progress.json()["attempts"], 4)
        self.assertEqual(reopened_profile.status_code, 200)
        self.assertEqual(reopened_progress.json()["attempts"], 4)
        self.assertEqual(reopened_lessons.status_code, 200)
        self.assertTrue(reopened_lessons.json()[0]["completed"])

    def test_all_exercise_types_are_graded_and_saved(self):
        headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 4002)}
        payloads = [
            ("hello-basics", "hello-1", "hello"),
            ("hello-basics", "hello-2", "  NICE   TO MEET YOU "),
            ("about-me", "about-2", ["t1", "t2", "t3", "t4"]),
        ]
        with patch("app.dependencies.settings", self.telegram_settings):
            results = [
                self.client.post(
                    f"/api/v1/lessons/{lesson}/answer",
                    headers=headers,
                    json={"exercise_id": exercise, "answer": answer},
                )
                for lesson, exercise, answer in payloads
            ]
            wrong = self.client.post(
                "/api/v1/lessons/about-me/answer",
                headers=headers,
                json={"exercise_id": "about-2", "answer": ["t2", "t1", "t3", "t4"]},
            )
        self.assertTrue(all(result.status_code == 200 for result in results))
        self.assertTrue(all(result.json()["correct"] for result in results))
        self.assertFalse(wrong.json()["correct"])
        self.assertEqual(results[1].json()["correct_answer"], "Nice to meet you")
        with self.factory() as session:
            events = session.scalars(select(LearningEvent)).all()
            self.assertEqual(len(events), 4)
            self.assertEqual(sum(event.is_correct for event in events), 3)

    def test_progress_scoped_and_completion_is_unique_on_retries(self):
        first_headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 4010)}
        other_headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 4011)}
        with patch("app.dependencies.settings", self.telegram_settings):
            for exercise_id, answer in [
                ("hello-1", "hello"),
                ("hello-2", "Nice to meet you"),
            ]:
                response = self.client.post(
                    "/api/v1/lessons/hello-basics/answer",
                    headers=first_headers,
                    json={"exercise_id": exercise_id, "answer": answer},
                )
                self.assertTrue(response.json()["correct"])
            for exercise_id, answer in [
                ("hello-3", "fine"),
                ("hello-4", "My name is Lena"),
            ]:
                response = self.client.post(
                    "/api/v1/lessons/hello-basics/answer",
                    headers=first_headers,
                    json={"exercise_id": exercise_id, "answer": answer},
                )
                self.assertTrue(response.json()["correct"])
            # Retrying a successful answer records a new attempt but never creates
            # another lesson completion.
            self.client.post(
                "/api/v1/lessons/hello-basics/answer",
                headers=first_headers,
                json={"exercise_id": "hello-1", "answer": "hello"},
            )
            own_progress = self.client.get("/api/v1/progress", headers=first_headers)
            own_completed = self.client.get(
                "/api/v1/progress/lessons", headers=first_headers
            )
            other_progress = self.client.get("/api/v1/progress", headers=other_headers)
        self.assertEqual(own_progress.json()["attempts"], 5)
        self.assertEqual(own_progress.json()["correct_answers"], 5)
        self.assertEqual(len(own_completed.json()), 1)
        self.assertEqual(other_progress.json()["attempts"], 0)
        with self.factory() as session:
            self.assertEqual(len(session.scalars(select(LessonProgress)).all()), 1)

    def test_invalid_answers_resources_and_authentication(self):
        with patch("app.dependencies.settings", self.telegram_settings):
            unauthorized = self.client.get("/api/v1/courses")
            headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 4020)}
            missing = self.client.get("/api/v1/courses/missing", headers=headers)
            missing_lesson = self.client.get("/api/v1/lessons/missing", headers=headers)
            invalid_option = self.client.post(
                "/api/v1/lessons/hello-basics/answer",
                headers=headers,
                json={"exercise_id": "hello-1", "answer": "not-an-option"},
            )
            invalid_order = self.client.post(
                "/api/v1/lessons/about-me/answer",
                headers=headers,
                json={"exercise_id": "about-2", "answer": ["t1", "t1", "t3", "t4"]},
            )
            invalid_body = self.client.post(
                "/api/v1/lessons/about-me/answer",
                headers=headers,
                json={"exercise_id": "about-2", "answer": "I am"},
            )
            with self.factory() as session:
                exercise = session.scalar(
                    select(Exercise).where(Exercise.slug == "routine-1")
                )
                exercise.is_available = False
                session.commit()
            unavailable = self.client.post(
                "/api/v1/lessons/daily-routine/answer",
                headers=headers,
                json={"exercise_id": "routine-1", "answer": "whatever"},
            )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing_lesson.status_code, 404)
        self.assertEqual(invalid_option.status_code, 422)
        self.assertEqual(invalid_order.status_code, 422)
        self.assertEqual(invalid_body.status_code, 422)
        self.assertEqual(unavailable.status_code, 404)

    def test_content_seeding_is_idempotent(self):
        with self.factory() as session:
            self.assertEqual(
                seed_content(session), {"courses": 1, "lessons": 30, "exercises": 120}
            )
            self.assertEqual(
                seed_content(session), {"courses": 1, "lessons": 30, "exercises": 120}
            )
            self.assertEqual(len(session.scalars(select(Course)).all()), 1)
            self.assertEqual(len(session.scalars(select(Exercise)).all()), 120)

    def test_new_lesson_completes_and_adds_personal_vocabulary(self):
        owner = {"X-Telegram-Init-Data": signed_data("fixture-token", 8001)}
        other = {"X-Telegram-Init-Data": signed_data("fixture-token", 8002)}
        answers = [
            ("home-rooms-1", "is"),
            ("home-rooms-2", "The kitchen is next to the living room"),
            ("home-rooms-3", ["t1", "t2", "t3", "t4", "t5", "t6", "t7"]),
            ("home-rooms-4", "under"),
        ]
        with patch("app.dependencies.settings", self.telegram_settings):
            lesson = self.client.get("/api/v1/lessons/home-rooms", headers=owner)
            results = [
                self.client.post(
                    "/api/v1/lessons/home-rooms/answer",
                    headers=owner,
                    json={"exercise_id": slug, "answer": answer},
                )
                for slug, answer in answers
            ]
            owner_vocab = self.client.get("/api/v1/vocabulary", headers=owner).json()
            other_vocab = self.client.get("/api/v1/vocabulary", headers=other).json()
        self.assertEqual(lesson.status_code, 200)
        self.assertTrue(
            all(
                result.status_code == 200 and result.json()["correct"]
                for result in results
            )
        )
        self.assertTrue(results[-1].json()["lesson_completed"])
        intended = {"bedroom", "kitchen", "table", "next to"}
        self.assertTrue(intended.issubset({item["word"] for item in owner_vocab}))
        self.assertFalse(intended & {item["word"] for item in other_vocab})

    def test_completed_lesson_adds_personal_words_once_and_survives_reseed(self):
        headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 51901)}
        with patch("app.dependencies.settings", self.telegram_settings):
            for exercise_id, answer in [
                ("hello-1", "hello"),
                ("hello-2", "nice to meet you"),
                ("hello-3", "fine"),
                ("hello-4", "My name is Lena"),
            ]:
                response = self.client.post(
                    "/api/v1/lessons/hello-basics/answer",
                    headers=headers,
                    json={"exercise_id": exercise_id, "answer": answer},
                )
                self.assertEqual(response.status_code, 200)
            for exercise_id, answer in [
                ("about-1", "is"),
                ("about-2", ["t1", "t2", "t3", "t4"]),
                ("about-3", "I am a student"),
                ("about-4", "name"),
            ]:
                response = self.client.post(
                    "/api/v1/lessons/about-me/answer",
                    headers=headers,
                    json={"exercise_id": exercise_id, "answer": answer},
                )
                self.assertEqual(response.status_code, 200)
            vocabulary_before = self.client.get("/api/v1/vocabulary", headers=headers)
            with self.factory() as db:
                reviewed = db.scalar(
                    select(VocabularyItem).where(VocabularyItem.user_id == 1)
                )
                reviewed.successful_reviews = 2
                reviewed.interval_days = 14
                db.commit()
                seed_content(db)
                seed_content(db)
            vocabulary_after = self.client.get("/api/v1/vocabulary", headers=headers)
        self.assertEqual(vocabulary_before.status_code, 200)
        self.assertEqual(vocabulary_after.status_code, 200)
        self.assertEqual(
            len(vocabulary_before.json()),
            9,
            [item["word"] for item in vocabulary_before.json()],
        )
        self.assertEqual(len(vocabulary_after.json()), 9)
        self.assertTrue(
            {"hello", "goodbye", "name", "meet"}.issubset(
                {item["word"] for item in vocabulary_after.json()}
            )
        )
        with self.factory() as db:
            items = db.scalars(
                select(VocabularyItem).where(VocabularyItem.user_id == 1)
            ).all()
            self.assertEqual(len(items), 9)
            self.assertEqual(len({item.word.casefold() for item in items}), 9)
            reviewed = next(item for item in items if item.source_key == "legacy:hello")
            self.assertEqual(reviewed.successful_reviews, 2)
            self.assertEqual(reviewed.interval_days, 14)

    def test_vocabulary_review_requires_reveal_and_saves_personal_schedule(self):
        owner_headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 50101)}
        other_headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 50102)}
        with patch("app.dependencies.settings", self.telegram_settings):
            self.assertEqual(self.client.get("/api/v1/review/due").status_code, 401)
            due = self.client.get("/api/v1/review/due", headers=owner_headers)
            self.assertEqual(due.status_code, 200)
            self.assertEqual(len(due.json()), 4)
            item = due.json()[0]
            self.assertNotIn("translation", item)
            self.assertNotIn("answer", item)

            before_reveal = self.client.post(
                f"/api/v1/vocabulary/{item['id']}/review",
                headers=owner_headers,
                json={"rating": "good"},
            )
            revealed = self.client.get(
                f"/api/v1/vocabulary/{item['id']}/translation",
                headers=owner_headers,
            )
            reviewed = self.client.post(
                f"/api/v1/vocabulary/{item['id']}/review",
                headers=owner_headers,
                json={"rating": "good"},
            )
            repeated = self.client.post(
                f"/api/v1/vocabulary/{item['id']}/review",
                headers=owner_headers,
                json={"rating": "good"},
            )
            other_user_cannot_reveal = self.client.get(
                f"/api/v1/vocabulary/{item['id']}/translation",
                headers=other_headers,
            )
            other_user_cannot_review = self.client.post(
                f"/api/v1/vocabulary/{item['id']}/review",
                headers=other_headers,
                json={"rating": "easy"},
            )

        self.assertEqual(before_reveal.status_code, 409)
        self.assertEqual(revealed.status_code, 200)
        self.assertTrue(revealed.json()["translation"])
        self.assertEqual(reviewed.status_code, 200)
        body = reviewed.json()
        self.assertEqual(body["rating"], "good")
        self.assertEqual(body["successful_reviews"], 1)
        self.assertEqual(body["failed_reviews"], 0)
        self.assertEqual(body["interval_days"], 2)
        self.assertTrue(datetime.fromisoformat(body["next_review_at"]).tzinfo)
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(other_user_cannot_reveal.status_code, 404)
        self.assertEqual(other_user_cannot_review.status_code, 404)
        with self.factory() as db:
            saved = db.get(VocabularyItem, item["id"])
            self.assertEqual(saved.successful_reviews, 1)
            self.assertEqual(saved.failed_reviews, 0)
            self.assertIsNone(saved.translation_revealed_at)

    def test_due_list_excludes_future_words_and_rating_validation_is_strict(self):
        headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 50103)}
        with patch("app.dependencies.settings", self.telegram_settings):
            first = self.client.get("/api/v1/review/due", headers=headers)
            future_id = first.json()[0]["id"]
            with self.factory() as db:
                item = db.get(VocabularyItem, future_id)
                item.next_review_at = datetime.now(timezone.utc) + timedelta(days=2)
                db.commit()
            due = self.client.get("/api/v1/review/due", headers=headers)
            invalid_rating = self.client.post(
                f"/api/v1/vocabulary/{first.json()[1]['id']}/review",
                headers=headers,
                json={"rating": "perfect"},
            )
            malformed_rating = self.client.post(
                f"/api/v1/vocabulary/{first.json()[1]['id']}/review",
                headers=headers,
                json={"rating": "good", "next_review_at": "2099-01-01T00:00:00Z"},
            )
            unknown = self.client.post(
                "/api/v1/vocabulary/999999/review",
                headers=headers,
                json={"rating": "good"},
            )
        self.assertEqual(len(due.json()), 3)
        self.assertNotIn(future_id, [item["id"] for item in due.json()])
        self.assertEqual(invalid_rating.status_code, 422)
        self.assertEqual(malformed_rating.status_code, 422)
        self.assertEqual(unknown.status_code, 404)

    def test_again_rating_tracks_failure_and_schedules_early_retry(self):
        headers = {"X-Telegram-Init-Data": signed_data("fixture-token", 50104)}
        with patch("app.dependencies.settings", self.telegram_settings):
            item = self.client.get("/api/v1/review/due", headers=headers).json()[0]
            self.client.get(
                f"/api/v1/vocabulary/{item['id']}/translation", headers=headers
            )
            result = self.client.post(
                f"/api/v1/vocabulary/{item['id']}/review",
                headers=headers,
                json={"rating": "again"},
            )
            dashboard = self.client.get("/api/v1/dashboard", headers=headers).json()
        self.assertEqual(result.status_code, 200)
        body = result.json()
        self.assertEqual(body["successful_reviews"], 0)
        self.assertEqual(body["failed_reviews"], 1)
        self.assertEqual(body["consecutive_successes"], 0)
        self.assertEqual(body["interval_days"], 0)
        next_review = datetime.fromisoformat(body["next_review_at"])
        last_reviewed = datetime.fromisoformat(body["last_reviewed_at"])
        self.assertEqual(next_review - last_reviewed, timedelta(minutes=10))
        self.assertEqual(dashboard["today"]["vocabulary_review_actions"], 1)
        self.assertEqual(dashboard["stats"]["vocabulary_review_submissions"], 1)


if __name__ == "__main__":
    unittest.main()
