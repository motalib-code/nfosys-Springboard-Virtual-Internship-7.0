from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.core.deps import get_db, require_role, get_current_user
from app.models import User, UserRole, QuestionType, Difficulty
from app.schemas.question import (
    QuestionCreate, QuestionUpdate, QuestionOut, QuestionListResponse
)
from app.services.question_service import QuestionService

router = APIRouter(prefix="/questions", tags=["Question Bank"])


@router.post("", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
def create_question(
    question_in: QuestionCreate,
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    return QuestionService.create_question(db, question_in, current_user)


@router.get("", response_model=QuestionListResponse)
def list_questions(
    subject: Optional[str] = None,
    difficulty: Optional[Difficulty] = None,
    question_type: Optional[QuestionType] = None,
    tag: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    items, total = QuestionService.list_questions(
        db,
        subject=subject,
        difficulty=difficulty,
        question_type=question_type,
        tag=tag,
        page=page,
        size=size
    )
    return QuestionListResponse(items=items, total=total, page=page, size=size)


@router.get("/{id}", response_model=QuestionOut)
def get_question(
    id: str,
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    return QuestionService.get_question(db, id)


@router.put("/{id}", response_model=QuestionOut)
def update_question(
    id: str,
    question_in: QuestionUpdate,
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    return QuestionService.update_question(db, id, question_in, current_user)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    id: str,
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    QuestionService.delete_question(db, id, current_user)
    return None
