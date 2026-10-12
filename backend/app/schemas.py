from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SettingsPatch(BaseModel):
    ui_language: str | None = Field(default=None, pattern="^(ru|en)$")
    daily_goal: int | None = Field(default=None, ge=5, le=60)

    @model_validator(mode="after")
    def reject_explicit_null(self):
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class AnswerSubmission(BaseModel):
    exercise_id: str = Field(min_length=1, max_length=80)
    answer: str | list[str] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_answer(self):
        if isinstance(self.answer, str) and not self.answer.strip():
            raise ValueError("answer must not be blank")
        if isinstance(self.answer, list):
            if len(self.answer) > 30 or any(
                not item.strip() or len(item) > 80 for item in self.answer
            ):
                raise ValueError("answer must contain 1 to 30 non-empty token IDs")
        return self


class ReviewRating(str, Enum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class VocabularyReviewSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: ReviewRating


class DueVocabularyItem(BaseModel):
    id: int
    word: str
    next_review_at: datetime


class VocabularyReviewResult(BaseModel):
    id: int
    word: str
    translation: str
    rating: ReviewRating
    successful_reviews: int
    failed_reviews: int
    consecutive_successes: int
    interval_days: int
    last_reviewed_at: datetime
    next_review_at: datetime
