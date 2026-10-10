from typing import List, Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import GradingQueueStatus


class QueueItemOut(BaseModel):
    id: str
    answer_id: str
    session_id: str
    exam_id: str
    status: GradingQueueStatus
    priority: int
    attempts: int
    claimed_by: Optional[str]
    claimed_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnswerGradeDetailOut(BaseModel):
    answer_id: str
    question_id: str
    question_text: str
    model_answer: Optional[str]
    student_text_answer: Optional[str]
    image_answer_url: Optional[str]
    thumbnail_url: Optional[str]
    ocr_text: Optional[str]
    max_marks: float
    current_marks_awarded: Optional[float]
    ai_suggestion: Optional[Dict[str, Any]]


class GradeAnswerRequest(BaseModel):
    marks_awarded: float = Field(..., ge=0.0)
    feedback_note: Optional[str] = None
