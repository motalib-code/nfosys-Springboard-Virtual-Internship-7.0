from typing import List, Optional
from fastapi import APIRouter, Depends, Query, UploadFile, File, status
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.core.deps import get_db, get_current_user
from app.models import User
from app.schemas.session import (
    ExamPaperResponse, AnswerSubmitRequest, AnswerOut,
    ProctorEventCreate, ProctorEventOut, SessionSubmitResponse,
    TimeRemainingResponse
)
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["Exam Sessions"])


@router.get("/{id}/time-remaining", response_model=TimeRemainingResponse)
def get_time_remaining(
    id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return SessionService.get_time_remaining(db, id, current_user)


@router.get("/{id}/paper", response_model=ExamPaperResponse)
def get_session_paper(
    id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return SessionService.get_session_paper(db, id, current_user)


@router.get("/{id}/answers", response_model=List[AnswerOut])
def get_student_answers(
    id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return SessionService.get_student_answers(db, id, current_user)


@router.put("/{id}/answers/{question_id}", response_model=AnswerOut)
def submit_answer_by_id(
    id: str,
    question_id: str,
    answer_in: AnswerSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    answer_in.question_id = question_id
    return SessionService.submit_answer(db, id, answer_in, current_user)


@router.post("/{id}/answers", response_model=AnswerOut)
def submit_answer(
    id: str,
    answer_in: AnswerSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return SessionService.submit_answer(db, id, answer_in, current_user)


@router.post("/{id}/answers/{question_id}/image", response_model=AnswerOut)
async def upload_image_answer(
    id: str,
    question_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    file_bytes = await file.read()
    return SessionService.upload_image_answer(
        db, id, question_id, file_bytes, file.filename or "image.jpg", current_user
    )


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
