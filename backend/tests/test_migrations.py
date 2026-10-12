import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from datetime import datetime, timezone

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import create_database_engine
from app.models import (
    Course,
    Exercise,
    Lesson,
    LessonProgress,
    User,
    UserSettings,
    VocabularyItem,
)
from app.content_quality import validate_seeded_records
from app.seed_content import load_content, seed_content
from app.vocabulary_review import as_utc


class MigrationTests(unittest.TestCase):
    def run_upgrade(self, database_path: Path, revision: str = "head"):
        config = Config("alembic.ini")
        config.attributes["database_url"] = f"sqlite:///{database_path.as_posix()}"
        command.upgrade(config, revision)

    def test_clean_database_is_created_by_migration(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "clean.db"
            self.run_upgrade(path)
            engine = create_database_engine(f"sqlite:///{path.as_posix()}")
            inspector = inspect(engine)
            self.assertTrue(
                {
                    "users",
                    "user_settings",
                    "learning_events",
                    "vocabulary_items",
                    "courses",
                    "lessons",
                    "exercises",
                    "lesson_progress",
                    "learning_activities",
                    "alembic_version",
                }.issubset(inspector.get_table_names())
            )
            self.assertTrue(inspector.get_foreign_keys("user_settings"))
            self.assertTrue(inspector.get_foreign_keys("lessons"))
            self.assertTrue(inspector.get_foreign_keys("exercises"))
            self.assertTrue(inspector.get_foreign_keys("lesson_progress"))
            with engine.connect() as connection:
                self.assertEqual(
                    connection.exec_driver_sql("PRAGMA foreign_keys").scalar(), 1
                )
            engine.dispose()

            # Running upgrade again must be a no-op and preserve the schema.
            self.run_upgrade(path)
            engine = create_database_engine(f"sqlite:///{path.as_posix()}")
            self.assertTrue(inspect(engine).has_table("lesson_progress"))
            engine.dispose()

    def test_seed_is_idempotent_on_alembic_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "seeded.db"
            self.run_upgrade(path)
            engine = create_database_engine(f"sqlite:///{path.as_posix()}")
            factory = sessionmaker(bind=engine)
            with factory() as db:
                seed_content(db)
                lesson = db.scalar(select(Lesson).where(Lesson.slug == "hello-basics"))
                user = User(
                    telegram_id=987657,
                    first_name="Preserve progress",
                    settings=UserSettings(),
                )
                db.add(user)
                db.flush()
                progress = LessonProgress(user_id=user.id, lesson_id=lesson.id)
                review_due = datetime(2030, 1, 2, tzinfo=timezone.utc)
                vocabulary = VocabularyItem(
                    user_id=user.id,
                    word="remember",
                    translation="помнить",
                    source_key="fixture:remember",
                    next_review_at=review_due,
                    successful_reviews=2,
                    failed_reviews=1,
                    consecutive_successes=2,
                    interval_days=14,
                    last_reviewed_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
                    last_rating="good",
                )
                db.add_all([progress, vocabulary])
                db.commit()
                progress_id = progress.id
                vocabulary_id = vocabulary.id
                seed_content(db)
                self.assertEqual(len(db.scalars(select(Course)).all()), 1)
                self.assertEqual(len(db.scalars(select(Exercise)).all()), 120)
                self.assertEqual(len(db.scalars(select(Lesson)).all()), 30)
                validate_seeded_records(db, load_content())
                preserved_progress = db.get(LessonProgress, progress_id)
                preserved_vocabulary = db.get(VocabularyItem, vocabulary_id)
                self.assertIsNotNone(preserved_progress)
                self.assertEqual(preserved_vocabulary.successful_reviews, 2)
                self.assertEqual(preserved_vocabulary.failed_reviews, 1)
                self.assertEqual(preserved_vocabulary.interval_days, 14)
                self.assertEqual(
                    as_utc(preserved_vocabulary.next_review_at), review_due
                )
            engine.dispose()

    def test_legacy_tables_and_user_data_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.db"
            self.run_upgrade(path, "0001_initial")
            engine = create_database_engine(f"sqlite:///{path.as_posix()}")
            with Session(engine) as db:
                user = User(
                    telegram_id=987654, first_name="Keep", settings=UserSettings()
                )
                db.add(user)
                db.commit()
                user_id = user.id
            self.run_upgrade(path)
            with Session(engine) as db:
                preserved = db.scalar(select(User).where(User.id == user_id))
                self.assertEqual(preserved.telegram_id, 987654)
                self.assertEqual(preserved.first_name, "Keep")
                self.assertIsNotNone(preserved.settings)
                self.assertEqual(preserved.settings.ui_language, "ru")
                self.assertEqual(preserved.settings.target_language, "en")
            engine.dispose()

    def test_vocabulary_rows_survive_review_state_migration(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "vocabulary.db"
            self.run_upgrade(path, "0002_learning_engine")
            engine = create_database_engine(f"sqlite:///{path.as_posix()}")
            due_at = datetime(2026, 2, 3, 4, 5, tzinfo=timezone.utc)
            with Session(engine) as db:
                user = User(
                    telegram_id=987655, first_name="Keep vocab", settings=UserSettings()
                )
                db.add(user)
                db.flush()
                db.connection().exec_driver_sql(
                    "INSERT INTO vocabulary_items (user_id, word, translation, next_review_at) "
                    "VALUES (?, ?, ?, ?)",
                    (user.id, "preserve", "сохранить", due_at.isoformat()),
                )
                db.commit()
                item_id = (
                    db.connection()
                    .exec_driver_sql(
                        "SELECT id FROM vocabulary_items WHERE word = ?", ("preserve",)
                    )
                    .scalar_one()
                )
            engine.dispose()

            self.run_upgrade(path)
            engine = create_database_engine(f"sqlite:///{path.as_posix()}")
            with Session(engine) as db:
                item = db.get(VocabularyItem, item_id)
                self.assertEqual(item.word, "preserve")
                self.assertEqual(item.translation, "сохранить")
                self.assertEqual(db.get(User, item.user_id).telegram_id, 987655)
                self.assertEqual(item.successful_reviews, 0)
                self.assertEqual(item.failed_reviews, 0)
                self.assertEqual(item.consecutive_successes, 0)
                self.assertEqual(item.interval_days, 0)
                self.assertIsNone(item.last_reviewed_at)
                self.assertIsNone(item.last_rating)
                self.assertIsNone(item.translation_revealed_at)
                self.assertEqual(as_utc(item.next_review_at), due_at)
            engine.dispose()

    def test_new_lesson_vocabulary_migration_preserves_existing_review_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stage5.db"
            self.run_upgrade(path, "0003_vocabulary_review_state")
            engine = create_database_engine(f"sqlite:///{path.as_posix()}")
            with Session(engine) as db:
                user = User(
                    telegram_id=987656, first_name="Retain", settings=UserSettings()
                )
                db.add(user)
                db.flush()
                db.connection().exec_driver_sql(
                    "INSERT INTO vocabulary_items (user_id, word, translation, next_review_at, successful_reviews, failed_reviews, consecutive_successes, interval_days) "
                    "VALUES (?, ?, ?, ?, 0, 0, 0, 0)",
                    (
                        user.id,
                        "hello",
                        "привет",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                db.commit()
                item_id = (
                    db.connection()
                    .exec_driver_sql(
                        "SELECT id FROM vocabulary_items WHERE word = ?", ("hello",)
                    )
                    .scalar_one()
                )
            engine.dispose()
            self.run_upgrade(path)
            engine = create_database_engine(f"sqlite:///{path.as_posix()}")
            with Session(engine) as db:
                item = db.get(VocabularyItem, item_id)
                self.assertEqual(item.word, "hello")
                self.assertEqual(item.translation, "привет")
                self.assertIsNone(item.source_key)
                self.assertEqual(item.successful_reviews, 0)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
