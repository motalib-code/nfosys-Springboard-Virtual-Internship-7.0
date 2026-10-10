from typing import TypedDict, Optional, List, Dict, Any
from pydantic import BaseModel, Field

class GradeResult(BaseModel):
    suggested_score: float = Field(..., description="Suggested score for the answer")
    max_score: float = Field(..., description="Maximum possible score for the question")
    justification: str = Field(..., description="Justification for the grade (<= 3 sentences)")
    key_points_matched: List[str] = Field(default_factory=list, description="Key rubric points matched")
    key_points_missed: List[str] = Field(default_factory=list, description="Key rubric points missed")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0")

class GradingState(TypedDict):
    answer_id: str
    question_text: str
    marks: float
    model_answer: Optional[str]
    rubric_key_points: List[str]
    student_answer: str
    question_type: str
    image_bytes: Optional[bytes]
    ocr_text: Optional[str]
    ocr_confidence: Optional[float]
    llm_result: Optional[GradeResult]
    confidence: float
    status: str
    errors: List[str]
    attempts: int
