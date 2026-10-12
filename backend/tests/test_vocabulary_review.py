import unittest
from datetime import datetime, timedelta, timezone

from app.schemas import ReviewRating
from app.vocabulary_review import as_utc, calculate_schedule


class VocabularyScheduleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)

    def schedule(self, rating, *, streak=0, interval=0, successes=0, failures=0):
        return calculate_schedule(
            rating,
            successful_reviews=successes,
            failed_reviews=failures,
            consecutive_successes=streak,
            interval_days=interval,
            now=self.now,
        )

    def test_again_retries_in_ten_minutes_and_resets_success_streak(self):
        result = self.schedule(
            ReviewRating.AGAIN, streak=3, interval=12, successes=3, failures=1
        )
        self.assertEqual(result.next_review_at, self.now + timedelta(minutes=10))
        self.assertEqual(result.failed_reviews, 2)
        self.assertEqual(result.successful_reviews, 3)
        self.assertEqual(result.consecutive_successes, 0)
        self.assertEqual(result.interval_days, 0)

    def test_initial_intervals_are_ordered_hard_good_easy(self):
        hard = self.schedule(ReviewRating.HARD)
        good = self.schedule(ReviewRating.GOOD)
        easy = self.schedule(ReviewRating.EASY)
        self.assertEqual(
            (hard.interval_days, good.interval_days, easy.interval_days), (1, 2, 4)
        )
        self.assertLess(hard.next_review_at, good.next_review_at)
        self.assertLess(good.next_review_at, easy.next_review_at)
        self.assertEqual(
            (hard.successful_reviews, good.successful_reviews, easy.successful_reviews),
            (1, 1, 1),
        )

    def test_successive_intervals_increase_and_keep_relative_order(self):
        hard = self.schedule(ReviewRating.HARD, streak=1, interval=2)
        good = self.schedule(ReviewRating.GOOD, streak=1, interval=2)
        easy = self.schedule(ReviewRating.EASY, streak=1, interval=2)
        self.assertEqual(
            (hard.interval_days, good.interval_days, easy.interval_days), (3, 4, 5)
        )

    def test_long_intervals_are_bounded_and_easy_remains_longer_than_good(self):
        good = self.schedule(ReviewRating.GOOD, streak=8, interval=10000)
        easy = self.schedule(ReviewRating.EASY, streak=8, interval=10000)
        self.assertEqual(good.interval_days, 730)
        self.assertEqual(easy.interval_days, 1095)

    def test_utc_normalizes_naive_sqlite_timestamps(self):
        naive = datetime(2026, 1, 2, 3, 4)
        self.assertEqual(as_utc(naive), self.now)


if __name__ == "__main__":
    unittest.main()
