from typing import Optional, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.core.deps import get_db, require_role, get_current_user
from app.models import (
    User, UserRole, GradingQueue, Answer, QuestionBank, ExamSession, Exam,
    AIEvaluation, GradingAuditLog, GradingStatus, Result, GradingQueueStatus
)
from app.core.exceptions import NotFoundException, PermissionDeniedException, BadRequestException

router = APIRouter(prefix="/grading", tags=["Examiner Grading Portal"])

@router.get("/queue")
def list_grading_queue(
    exam_id: Optional[str] = Query(None),
    status_filter: Optional[GradingQueueStatus] = Query(None, alias="status"),
    question_type: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    query = db.query(GradingQueue)

    if exam_id:
        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        if not exam:
            raise NotFoundException("Exam not found")
        if current_user.role == UserRole.EXAMINER and exam.created_by != current_user.id:
            raise PermissionDeniedException("Access denied to another examiner's exam")
        query = query.filter(GradingQueue.exam_id == exam_id)

    if status_filter:
        query = query.filter(GradingQueue.status == status_filter)

    if cursor:
        query = query.filter(GradingQueue.id > cursor)

    items = query.order_by(GradingQueue.created_at.asc(), GradingQueue.id.asc()).limit(limit).all()

    return [{
        "queue_id": item.id,
        "answer_id": item.answer_id,
        "session_id": item.session_id,
        "exam_id": item.exam_id,
        "status": item.status,
        "attempts": item.attempts,
        "created_at": item.created_at
    } for item in items]


@router.get("/answers/{answer_id}")
def get_grading_answer_detail(
    answer_id: str,
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    ans = db.query(Answer).filter(Answer.id == answer_id).first()
    if not ans:
        raise NotFoundException("Answer not found")

    q = db.query(QuestionBank).filter(QuestionBank.id == ans.question_id).first()
    sess = db.query(ExamSession).filter(ExamSession.id == ans.session_id).first()
    exam = db.query(Exam).filter(Exam.id == sess.exam_id).first() if sess else None

    if current_user.role == UserRole.EXAMINER and exam and exam.created_by != current_user.id:
        raise PermissionDeniedException("Access denied")

    ai_eval = db.query(AIEvaluation).filter(AIEvaluation.answer_id == answer_id).order_by(AIEvaluation.created_at.desc()).first()

    return {
        "answer_id": ans.id,
        "session_id": ans.session_id,
        "question": {
            "id": q.id,
            "question_text": q.question_text,
            "question_type": q.question_type.value,
            "max_marks": q.marks,
            "model_answer": q.model_answer
        },
        "student_answer": {
            "text": ans.text_answer,
            "image_url": ans.image_answer_url,
            "thumbnail_url": ans.thumbnail_url
        },
        "ai_suggestion": {
            "suggested_score": ai_eval.suggested_score if ai_eval else None,
            "max_score": ai_eval.max_score if ai_eval else None,
            "justification": ai_eval.justification if ai_eval else None,
            "key_points_matched": ai_eval.key_points_matched if ai_eval else [],
            "key_points_missed": ai_eval.key_points_missed if ai_eval else [],
            "confidence": ai_eval.confidence if ai_eval else None,
            "ocr_text": ai_eval.ocr_text if ai_eval else None
        } if ai_eval else None,
        "marks_awarded": ans.marks_awarded,
        "graded_by": ans.graded_by,
        "graded_at": ans.graded_at
    }


@router.put("/grading/answers/{answer_id}", response_model=None)
@router.put("/answers/{answer_id}")
def finalize_manual_answer_grade(
    answer_id: str,
    marks_awarded: float = Query(..., ge=0.0),
    feedback: Optional[str] = Query(None),
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    ans = db.query(Answer).filter(Answer.id == answer_id).first()
    if not ans:
        raise NotFoundException("Answer not found")

    q = db.query(QuestionBank).filter(QuestionBank.id == ans.question_id).first()
    sess = db.query(ExamSession).filter(ExamSession.id == ans.session_id).first()
    exam = db.query(Exam).filter(Exam.id == sess.exam_id).first() if sess else None

    if current_user.role == UserRole.EXAMINER and exam and exam.created_by != current_user.id:
        raise PermissionDeniedException("Access denied")

    if marks_awarded > q.marks:
        raise BadRequestException(f"marks_awarded ({marks_awarded}) exceeds question max marks ({q.marks})")

    old_score = ans.marks_awarded
    now = datetime.now(timezone.utc)

    ans.marks_awarded = marks_awarded
    ans.graded_by = current_user.id
    ans.graded_at = now

    # Log audit entry
    audit = GradingAuditLog(
        answer_id=answer_id,
        actor_id=current_user.id,
        action="manual_grade_entry",
        old_score=old_score,
        new_score=marks_awarded,
        note=feedback,
        at=now
    )
    db.add(audit)

    # Update queue status
    q_item = db.query(GradingQueue).filter(GradingQueue.answer_id == answer_id).first()
    if q_item:
        q_item.status = GradingQueueStatus.GRADED
        q_item.updated_at = now

    db.commit()
    return {"message": "Answer grade finalized successfully", "answer_id": answer_id, "marks_awarded": marks_awarded}


@router.post("/exams/{exam_id}/finalize")
def finalize_exam_grading(
    exam_id: str,
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise NotFoundException("Exam not found")

    if current_user.role == UserRole.EXAMINER and exam.created_by != current_user.id:
        raise PermissionDeniedException("Access denied")

    sessions = db.query(ExamSession).filter(ExamSession.exam_id == exam_id).all()
    for s in sessions:
        res = db.query(Result).filter(Result.session_id == s.id).first()
        if res:
            res.grading_status = GradingStatus.FINAL
            res.updated_at = datetime.now(timezone.utc)

    db.commit()
    return {"message": f"Grading finalized for exam {exam_id}"}


@router.get("/answers/{answer_id}/ai-trace")
def get_answer_ai_trace(
    answer_id: str,
    current_user: User = Depends(require_role(UserRole.EXAMINER, UserRole.ADMIN)),
    db: Session = Depends(get_db)
):
    evals = db.query(AIEvaluation).filter(AIEvaluation.answer_id == answer_id).order_by(AIEvaluation.created_at.desc()).all()
    return [{
        "evaluation_id": ev.id,
        "model_name": ev.model_name,
        "prompt_version": ev.prompt_version,
        "suggested_score": ev.suggested_score,
        "confidence": ev.confidence,
        "ocr_text": ev.ocr_text,
        "ocr_confidence": ev.ocr_confidence,
        "created_at": ev.created_at
    } for ev in evals]
