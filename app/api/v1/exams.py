from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.core.deps import get_db, require_role, get_current_user
from app.models import User, UserRole, ExamStatus
from app.schemas.exam import (
    ExamCreate, ExamUpdate, ExamOut, ExamListResponse
)
from app.schemas.session import PaginatedProctorSessionsResponse
from app.services.exam_service import ExamService
from app.services.proctoring_service import ProctoringService

router = APIRouter(prefix="/exams", tags=["Exams"])


@router.post("", response_model=ExamOut, status_code=status.HTTP_201_CREATED)
def create_exam(
    exam_in: ExamCreate,
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    return ExamService.create_exam(db, exam_in, current_user)


@router.get("", response_model=ExamListResponse)
def list_exams(
    subject: Optional[str] = None,
    exam_status: Optional[ExamStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    items, total = ExamService.list_exams(
        db,
        subject=subject,
        status=exam_status,
        page=page,
        size=size
    )
    return ExamListResponse(items=items, total=total, page=page, size=size)


@router.get("/{id}/proctoring/sessions", response_model=PaginatedProctorSessionsResponse)
def get_exam_proctoring_sessions(
    id: str,
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    flagged_only: bool = Query(False),
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    return ProctoringService.get_exam_proctoring_sessions(
        db, id, current_user, limit=limit, cursor=cursor, flagged_only=flagged_only
    )


@router.get("/{id}", response_model=ExamOut)
def get_exam(
    id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return ExamService.get_exam(db, id)


@router.put("/{id}", response_model=ExamOut)
def update_exam(
    id: str,
    exam_in: ExamUpdate,
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    return ExamService.update_exam(db, id, exam_in, current_user)


@router.post("/{id}/publish", response_model=ExamOut)
def publish_exam(
    id: str,
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    return ExamService.publish_exam(db, id, current_user)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exam(
    id: str,
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    ExamService.delete_exam(db, id, current_user)
    return None
