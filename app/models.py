from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from typing import Literal

QuestionType = Literal["choose_meaning", "choose_word", "spell_word"]


class GenerateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=200)


class MeaningEntry(BaseModel):
    part_of_speech: str = ""
    english_meaning: str = ""
    chinese_translation: str = ""  # Concise direct Chinese translation (e.g. "細微的；微妙的").
    chinese_explanation: str = ""  # Longer Traditional Chinese explanation describing nuance and usage.
    example_sentence: str = ""
    example_translation: str = ""
    usage_note: str = ""


class VocabBase(BaseModel):
    input_text: str = Field(..., min_length=1, max_length=200)
    type: str = ""
    meanings: list[MeaningEntry] = Field(default_factory=list)
    pronunciation: str = ""
    similar_expressions: list[str] = Field(default_factory=list)
    difficulty: str = "medium"
    tags: list[str] = Field(default_factory=list)

    @field_validator("input_text")
    @classmethod
    def strip_input_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("input_text cannot be empty")
        return value


class VocabCreate(VocabBase):
    familiarity: int = Field(default=0, ge=0, le=5)


class VocabUpdate(BaseModel):
    input_text: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = None
    meanings: list[MeaningEntry] | None = None
    pronunciation: str | None = None
    similar_expressions: list[str] | None = None
    difficulty: str | None = None
    tags: list[str] | None = None
    familiarity: int | None = Field(default=None, ge=0, le=5)

    @field_validator("input_text")
    @classmethod
    def strip_optional_input_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("input_text cannot be empty")
        return value


class AnswerRequest(BaseModel):
    user_answer: str = Field(..., min_length=1)
