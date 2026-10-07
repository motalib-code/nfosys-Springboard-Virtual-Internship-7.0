from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional, List, Any
from datetime import datetime
from app.models.enums import QuestionType, Difficulty


class OptionCreate(BaseModel):
    option_text: str = Field(..., min_length=1)
    is_correct: bool = False
    display_order: Optional[int] = 0


class OptionOut(BaseModel):
    id: str
    option_text: str
    is_correct: bool
    display_order: int

    model_config = ConfigDict(from_attributes=True)


class QuestionCreate(BaseModel):
    question_type: QuestionType
    subject: str = Field(..., min_length=1)
    tags: Optional[List[str]] = Field(default_factory=list)
    difficulty: Difficulty
    question_text: str = Field(..., min_length=1)
    image_url: Optional[str] = None
    marks: float = Field(..., gt=0)
    negative_marks: float = Field(default=0.0, ge=0)
    model_answer: Optional[str] = None
    expected_answer: Optional[Any] = None
    max_marks_for_image: Optional[float] = None
    options: Optional[List[OptionCreate]] = None

    @model_validator(mode="after")
    def validate_question_rules(self):
        if self.negative_marks > self.marks:
            raise ValueError("negative_marks cannot be greater than marks")

        q_type = self.question_type

        if q_type == QuestionType.MCQ:
            if not self.options or len(self.options) < 2:
                raise ValueError("MCQ questions must have at least 2 options")
            correct_count = sum(1 for opt in self.options if opt.is_correct)
            if correct_count != 1:
                raise ValueError(f"MCQ questions must have EXACTLY ONE correct option. Found {correct_count}.")

        elif q_type == QuestionType.MULTI_SELECT:
            if not self.options or len(self.options) < 2:
                raise ValueError("multi_select questions must have at least 2 options")
            correct_count = sum(1 for opt in self.options if opt.is_correct)
            if correct_count < 1:
                raise ValueError("multi_select questions must have at least 1 correct option")

        elif q_type in [QuestionType.SHORT_ANSWER, QuestionType.LONG_ANSWER]:
            if not self.model_answer or not self.model_answer.strip():
                raise ValueError(f"{q_type.value} questions require a model_answer")

        elif q_type == QuestionType.IMAGE_UPLOAD:
            # Check max_marks_for_image or marks > 0 and defined
            target_max = self.max_marks_for_image if self.max_marks_for_image is not None else self.marks
            if target_max is None or target_max <= 0:
                raise ValueError("image_upload questions require max_marks_for_image / marks to be defined and > 0")

        return self


class QuestionUpdate(BaseModel):
    subject: Optional[str] = None
    tags: Optional[List[str]] = None
    difficulty: Optional[Difficulty] = None
    question_text: Optional[str] = None
    image_url: Optional[str] = None
    marks: Optional[float] = Field(None, gt=0)
    negative_marks: Optional[float] = Field(None, ge=0)
    model_answer: Optional[str] = None
    expected_answer: Optional[Any] = None
    max_marks_for_image: Optional[float] = None
    options: Optional[List[OptionCreate]] = None
    is_active: Optional[bool] = None


class QuestionOut(BaseModel):
    id: str
    created_by: Optional[str]
    question_type: QuestionType
    subject: str
    tags: Optional[List[str]]
    difficulty: Difficulty
    question_text: str
    image_url: Optional[str]
    marks: float
    negative_marks: float
    model_answer: Optional[str]
    expected_answer: Optional[Any]
    max_marks_for_image: Optional[float]
    is_active: bool
    options: List[OptionOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class QuestionListResponse(BaseModel):
    items: List[QuestionOut]
    total: int
    page: int
    size: int
