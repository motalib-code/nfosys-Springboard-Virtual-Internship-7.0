from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from app.models.enums import SessionStatus, ProctorEventType


class AnswerSubmitRequest(BaseModel):
    question_id: str
    selected_option_ids: Optional[List[str]] = None
    text_answer: Optional[str] = None
    image_answer_url: Optional[str] = None


class AnswerUpsertRequest(BaseModel):
    selected_option_ids: Optional[List[str]] = None
    text_answer: Optional[str] = None


class AnswerOut(BaseModel):
    id: str
    session_id: str
    question_id: str
    selected_option_ids: Optional[List[str]] = None
    text_answer: Optional[str] = None
    word_count: Optional[int] = None
    image_answer_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    answered_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProctorEventCreate(BaseModel):
    event_type: ProctorEventType
    payload: Optional[Dict[str, Any]] = None
    severity: Optional[str] = "warning"


class ProctorEventOut(BaseModel):
    id: str
    session_id: str
    event_type: ProctorEventType
    timestamp: datetime
    payload: Optional[Dict[str, Any]]
    severity: str

    model_config = ConfigDict(from_attributes=True)


class ExamPaperResponse(BaseModel):
    session_id: str
    status: SessionStatus
    paper: Dict[str, Any]


class SessionSubmitResponse(BaseModel):
    session_id: str
    status: SessionStatus
    submitted_at: datetime


class TimeRemainingResponse(BaseModel):
    session_id: str
    seconds_remaining: int
    server_time: datetime
    server_deadline: Optional[datetime] = None
    status: SessionStatus


class ProctorPrecheckRequest(BaseModel):
    face_present: bool
    face_count: int


class SessionProctorSummary(BaseModel):
    session_id: str
    student_id: str
    student_name: str
    student_email: str
    status: SessionStatus
    suspicion_score: float
    is_flagged: bool
    tab_switch_count: int
    started_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedProctorSessionsResponse(BaseModel):
    sessions: List[SessionProctorSummary]
    next_cursor: Optional[str] = None
