from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.core.deps import get_db, get_current_user, require_role
from app.models import (
    User, UserRole, Answer, QuestionBank, Exam, ExamQuestion, ExamSession, Result,
    AIEvaluation, GradingQueue, GradingAuditLog, GradingQueueStatus, GradingStatus
)
from app.schemas.grading import QueueItemOut, AnswerGradeDetailOut, GradeAnswerRequest
from app.core.exceptions import NotFoundException, PermissionDeniedException, BadRequestException

router = APIRouter(prefix="/grading", tags=["Examiner Grading Portal"])


@router.get("/queue", response_model=List[QueueItemOut])
def get_grading_queue(
    exam_id: str,
    status_filter: Optional[GradingQueueStatus] = Query(None, alias="status"),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role([UserRole.EXAMINER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise NotFoundException("Exam not found")

    if current_user.role == UserRole.EXAMINER and exam.created_by != current_user.id:
        raise PermissionDeniedException("Cannot view grading queue for another examiner's exam")

    query = db.query(GradingQueue).filter(GradingQueue.exam_id == exam_id)
    if status_filter:
        query = query.filter(GradingQueue.status == status_filter)

    if cursor:
        query = query.filter(GradingQueue.id > cursor)

    items = query.order_by(GradingQueue.created_at.asc(), GradingQueue.id.asc()).limit(limit).all()
    return items


@router.get("/answers/{answer_id}", response_model=AnswerGradeDetailOut)
def get_answer_for_grading(
    answer_id: str,
    current_user: User = Depends(require_role([UserRole.EXAMINER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    ans = db.query(Answer).filter(Answer.id == answer_id).first()
    if not ans:
        raise NotFoundException("Answer not found")

    session = ans.session
    exam = session.exam
    if current_user.role == UserRole.EXAMINER and exam.created_by != current_user.id:
        raise PermissionDeniedException("Access denied")

    q = ans.question
    eq = db.query(ExamQuestion).filter(
        ExamQuestion.exam_id == exam.id,
        ExamQuestion.question_id == q.id
    ).first()
    max_marks = eq.marks_override if (eq and eq.marks_override is not None) else q.marks

    ai_eval = db.query(AIEvaluation).filter(AIEvaluation.answer_id == answer_id).order_by(AIEvaluation.created_at.desc()).first()
    ai_suggestion = None
    if ai_eval:
        ai_suggestion = {
            "model_name": ai_eval.model_name,
            "suggested_score": ai_eval.suggested_score,
            "max_score": ai_eval.max_score,
            "justification": ai_eval.justification,
            "key_points_matched": ai_eval.key_points_matched,
            "key_points_missed": ai_eval.key_points_missed,
            "confidence": ai_eval.confidence,
            "ocr_text": ai_eval.ocr_text
        }

    return {
        "answer_id": ans.id,
        "question_id": q.id,
        "question_text": q.question_text,
        "model_answer": q.model_answer,
        "student_text_answer": ans.text_answer,
        "image_answer_url": ans.image_answer_url,
        "thumbnail_url": ans.thumbnail_url,
        "ocr_text": ai_eval.ocr_text if ai_eval else None,
        "max_marks": max_marks,
        "current_marks_awarded": ans.marks_awarded,
        "ai_suggestion": ai_suggestion
    }


@router.put("/answers/{answer_id}")
def grade_answer_manually(
    answer_id: str,
    grade_in: GradeAnswerRequest,
    current_user: User = Depends(require_role([UserRole.EXAMINER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    ans = db.query(Answer).filter(Answer.id == answer_id).first()
    if not ans:
        raise NotFoundException("Answer not found")

    session = ans.session
    exam = session.exam
    if current_user.role == UserRole.EXAMINER and exam.created_by != current_user.id:
        raise PermissionDeniedException("Access denied")

    q = ans.question
    eq = db.query(ExamQuestion).filter(
        ExamQuestion.exam_id == exam.id,
        ExamQuestion.question_id == q.id
    ).first()
    max_marks = eq.marks_override if (eq and eq.marks_override is not None) else q.marks

    if grade_in.marks_awarded < 0.0 or grade_in.marks_awarded > max_marks:
        raise BadRequestException(f"Marks awarded ({grade_in.marks_awarded}) out of bounds [0, {max_marks}]")

    old_score = ans.marks_awarded
    now = datetime.now(timezone.utc)

    ans.marks_awarded = grade_in.marks_awarded
    ans.graded_by = current_user.id
    ans.graded_at = now

    # Audit log
    audit = GradingAuditLog(
        answer_id=ans.id,
        actor_id=current_user.id,
        action="manual_grade",
        old_score=old_score,
        new_score=grade_in.marks_awarded,
        note=grade_in.feedback_note,
        at=now
    )
    db.add(audit)

    # Update queue status
    q_item = db.query(GradingQueue).filter(GradingQueue.answer_id == answer_id).first()
    if q_item:
        q_item.status = GradingQueueStatus.GRADED

    db.commit()
    return {"message": "Answer graded successfully", "answer_id": ans.id, "marks_awarded": grade_in.marks_awarded}


@router.post("/exams/{exam_id}/finalize")
def finalize_exam_grading(
    exam_id: str,
    current_user: User = Depends(require_role([UserRole.EXAMINER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise NotFoundException("Exam not found")

    if current_user.role == UserRole.EXAMINER and exam.created_by != current_user.id:
        raise PermissionDeniedException("Access denied")

    # Check if all subjective answers are graded
    unprocessed_queue = db.query(GradingQueue).filter(
        GradingQueue.exam_id == exam_id,
        GradingQueue.status != GradingQueueStatus.GRADED
    ).count()

    if unprocessed_queue > 0:
        raise BadRequestException(f"Cannot finalize exam: {unprocessed_queue} items in grading queue are not fully graded yet.")

    sessions = db.query(ExamSession).filter(ExamSession.exam_id == exam_id).all()
    from app.services.evaluation import evaluate_objective

    for session in sessions:
        res = evaluate_objective(db, session.id)
        res.grading_status = GradingStatus.FINAL
        res.published_at = datetime.now(timezone.utc)

    db.commit()
    return {"message": "Exam grading finalized and results published.", "exam_id": exam_id, "sessions_finalized": len(sessions)}


@router.get("/answers/{answer_id}/ai-trace")
def get_ai_trace(
    answer_id: str,
    current_user: User = Depends(require_role([UserRole.EXAMINER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    evals = db.query(AIEvaluation).filter(AIEvaluation.answer_id == answer_id).order_by(AIEvaluation.created_at.asc()).all()
    return [
        {
            "id": ev.id,
            "model_name": ev.model_name,
            "prompt_version": ev.prompt_version,
            "suggested_score": ev.suggested_score,
            "justification": ev.justification,
            "confidence": ev.confidence,
            "ocr_text": ev.ocr_text,
            "ocr_confidence": ev.ocr_confidence,
            "status": ev.status,
            "error": ev.error,
            "created_at": ev.created_at
        }
        for ev in evals
    ]
