from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.core.deps import get_db, get_current_user
from app.models import User
from app.schemas.session import (
    ExamPaperResponse, AnswerSubmitRequest, AnswerOut,
    ProctorEventCreate, ProctorEventOut, SessionSubmitResponse
)
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["Exam Sessions"])


@router.get("/{id}/paper", response_model=ExamPaperResponse)
def get_session_paper(
    id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return SessionService.get_session_paper(db, id, current_user)


@router.post("/{id}/answers", response_model=AnswerOut)
def submit_answer(
    id: str,
    answer_in: AnswerSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return SessionService.submit_answer(db, id, answer_in, current_user)


@router.post("/{id}/events", response_model=ProctorEventOut, status_code=status.HTTP_201_CREATED)
def record_proctor_event(
    id: str,
    event_in: ProctorEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return SessionService.record_proctor_event(db, id, event_in, current_user)


@router.post("/{id}/submit", response_model=SessionSubmitResponse)
def submit_session(
    id: str,
    auto_submit: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = SessionService.submit_exam_session(db, id, current_user, auto_submit=auto_submit)
    return {
        "session_id": session.id,
        "status": session.status,
        "submitted_at": session.submitted_at
    }
