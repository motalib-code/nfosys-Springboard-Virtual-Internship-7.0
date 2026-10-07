from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from app.models.enums import SessionStatus, ProctorEventType


class AnswerSubmitRequest(BaseModel):
    question_id: str
    selected_option_ids: Optional[List[str]] = None
    text_answer: Optional[str] = None
    image_answer_url: Optional[str] = None


class AnswerOut(BaseModel):
    id: str
    session_id: str
    question_id: str
    selected_option_ids: Optional[List[str]]
    text_answer: Optional[str]
    image_answer_url: Optional[str]
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
