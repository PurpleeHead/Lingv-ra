import unittest

from app.learning import normalize_text


class LearningNormalizationTests(unittest.TestCase):
    def test_normalization_collapses_spaces_and_case_without_removing_accents(self):
        self.assertEqual(normalize_text("  HELLO\tthere "), "hello there")
        self.assertEqual(normalize_text("café"), normalize_text("cafe\u0301"))
        self.assertNotEqual(normalize_text("café"), normalize_text("cafe"))


if __name__ == "__main__":
    unittest.main()
