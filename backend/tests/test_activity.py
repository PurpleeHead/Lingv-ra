import unittest
from datetime import date, datetime, timezone

from app.activity import calculate_current_streak, record_learning_activity
from app.db import Base, create_database_engine
from app.models import LearningActivity, User, UserSettings
from sqlalchemy import select
from sqlalchemy.orm import Session


class ActivityTests(unittest.TestCase):
    def test_streak_handles_today_yesterday_and_gaps(self):
        today = date(2026, 10, 12)
        self.assertEqual(calculate_current_streak(set(), today), 0)
        self.assertEqual(calculate_current_streak({today}, today), 1)
        self.assertEqual(
            calculate_current_streak({date(2026, 10, 10), date(2026, 10, 11)}, today), 2
        )
        self.assertEqual(
            calculate_current_streak({date(2026, 10, 9), date(2026, 10, 11)}, today), 1
        )

    def test_record_is_idempotent_per_action_and_utc_day(self):
        engine = create_database_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            user = User(telegram_id=901, first_name="Fixture", settings=UserSettings())
            db.add(user)
            db.flush()
            record_learning_activity(
                db,
                user.id,
                "exercise",
                "lesson:exercise",
                datetime(2026, 10, 12, 23, 30, tzinfo=timezone.utc),
            )
            record_learning_activity(
                db,
                user.id,
                "exercise",
                "lesson:exercise",
                datetime(2026, 10, 13, 0, 10, tzinfo=timezone.utc),
            )
            record_learning_activity(
                db,
                user.id,
                "exercise",
                "lesson:exercise",
                datetime(2026, 10, 12, 23, 50, tzinfo=timezone.utc),
            )
            rows = db.scalars(select(LearningActivity)).all()
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                {row.activity_date for row in rows},
                {date(2026, 10, 12), date(2026, 10, 13)},
            )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
