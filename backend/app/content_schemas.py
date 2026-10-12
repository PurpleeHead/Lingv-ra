from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Localized(StrictModel):
    ru: str = Field(min_length=1, max_length=1000)
    en: str = Field(min_length=1, max_length=1000)

    @field_validator("ru", "en")
    @classmethod
    def text_must_not_be_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("localized text must not be blank")
        return value


class ExerciseHints(StrictModel):
    level_1: Localized
    level_2: Localized


class Choice(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")
    text: Localized

    @field_validator("id")
    @classmethod
    def id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("choice ID must not be blank")
        return value


class Token(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")
    text: str = Field(min_length=1, max_length=120)

    @field_validator("text")
    @classmethod
    def token_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("token text must not be blank")
        return value

    @field_validator("id")
    @classmethod
    def id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("token ID must not be blank")
        return value


class LessonVocabularySeed(StrictModel):
    slug: str = Field(min_length=1, max_length=80)
    word: str = Field(min_length=1, max_length=120)
    translation: str = Field(min_length=1, max_length=160)

    @field_validator("slug", "word", "translation")
    @classmethod
    def vocabulary_fields_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("vocabulary fields must not be blank")
        return value


class ChoicePublicData(StrictModel):
    choices: list[Choice] = Field(min_length=2, max_length=20)


class ChoiceAnswerData(StrictModel):
    correct: str = Field(min_length=1, max_length=80)


class TextPublicData(StrictModel):
    placeholder: Localized


class TextAnswerData(StrictModel):
    accepted: list[str] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_accepted(self):
        if any(not value.strip() or len(value) > 500 for value in self.accepted):
            raise ValueError(
                "accepted answers must be non-empty strings up to 500 chars"
            )
        normalized = [" ".join(value.split()).casefold() for value in self.accepted]
        if len(normalized) != len(set(normalized)):
            raise ValueError("accepted answers must be unique after normalization")
        return self


class WordOrderPublicData(StrictModel):
    tokens: list[Token] = Field(min_length=2, max_length=30)


class WordOrderAnswerData(StrictModel):
    order: list[str] = Field(min_length=2, max_length=30)


class ChoiceExercise(StrictModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")
    type: Literal["choice"]
    instruction: Localized
    prompt: Localized
    public_data: ChoicePublicData
    answer_data: ChoiceAnswerData
    explanation: Localized
    hints: ExerciseHints
    sort_order: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_choice(self):
        ids = [choice.id for choice in self.public_data.choices]
        if len(ids) != len(set(ids)) or self.answer_data.correct not in ids:
            raise ValueError("choice IDs must be unique and include the correct option")
        for language in ("ru", "en"):
            labels = [
                " ".join(getattr(choice.text, language).split()).casefold()
                for choice in self.public_data.choices
            ]
            if len(labels) != len(set(labels)):
                raise ValueError("choice labels must be unique in each language")
        return self


class TextExercise(StrictModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")
    type: Literal["text"]
    instruction: Localized
    prompt: Localized
    public_data: TextPublicData
    answer_data: TextAnswerData
    explanation: Localized
    hints: ExerciseHints
    sort_order: int = Field(ge=0)


class WordOrderExercise(StrictModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")
    type: Literal["word_order"]
    instruction: Localized
    prompt: Localized
    public_data: WordOrderPublicData
    answer_data: WordOrderAnswerData
    explanation: Localized
    hints: ExerciseHints
    sort_order: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_word_order(self):
        ids = [token.id for token in self.public_data.tokens]
        order = self.answer_data.order
        if (
            len(ids) != len(set(ids))
            or len(order) != len(set(order))
            or sorted(order) != sorted(ids)
        ):
            raise ValueError(
                "word_order IDs must be unique and order must use every token"
            )
        return self


ExerciseSeed = Annotated[
    ChoiceExercise | TextExercise | WordOrderExercise,
    Field(discriminator="type"),
]


class LessonSeed(StrictModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")
    title: Localized
    description: Localized
    sort_order: int = Field(ge=0)
    is_available: bool
    vocabulary: list[LessonVocabularySeed] = Field(default_factory=list, max_length=100)
    exercises: list[ExerciseSeed] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_exercises(self):
        slugs = [exercise.slug for exercise in self.exercises]
        orders = [exercise.sort_order for exercise in self.exercises]
        if len(slugs) != len(set(slugs)) or len(orders) != len(set(orders)):
            raise ValueError(
                "exercise slugs and sort orders must be unique within lesson"
            )
        vocabulary_slugs = [item.slug for item in self.vocabulary]
        if len(vocabulary_slugs) != len(set(vocabulary_slugs)):
            raise ValueError("vocabulary slugs must be unique within lesson")
        return self


class CourseSeed(StrictModel):
    slug: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")
    title: Localized
    description: Localized
    source_language: Literal["ru"]
    target_language: Literal["en"]
    level: str = Field(min_length=2, max_length=8)
    sort_order: int = Field(ge=0)
    is_published: bool


class ContentSeed(StrictModel):
    course: CourseSeed
    lessons: list[LessonSeed] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_lessons(self):
        slugs = [lesson.slug for lesson in self.lessons]
        orders = [lesson.sort_order for lesson in self.lessons]
        if len(slugs) != len(set(slugs)) or len(orders) != len(set(orders)):
            raise ValueError(
                "lesson slugs and sort orders must be unique within course"
            )
        exercise_slugs = [
            exercise.slug for lesson in self.lessons for exercise in lesson.exercises
        ]
        if len(exercise_slugs) != len(set(exercise_slugs)):
            raise ValueError("exercise slugs must be unique across the course")
        vocabulary_keys = [
            (lesson.slug, item.slug)
            for lesson in self.lessons
            for item in lesson.vocabulary
        ]
        if len(vocabulary_keys) != len(set(vocabulary_keys)):
            raise ValueError("vocabulary keys must be unique across the course")
        for lesson in self.lessons:
            fingerprints = [
                (
                    exercise.type,
                    " ".join(exercise.prompt.ru.split()).casefold(),
                    " ".join(exercise.prompt.en.split()).casefold(),
                )
                for exercise in lesson.exercises
            ]
            if len(fingerprints) != len(set(fingerprints)):
                raise ValueError(
                    f"lesson {lesson.slug} contains duplicate exercises of the same type and prompt"
                )
        return self
