from typing import Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import (
    ExamSession, Exam, QuestionBank, Answer, Option, Result, ExamQuestion,
    QuestionType, GradingStatus
)
from app.services.scoring_strategies import AllOrNothingStrategy, ScoringStrategy
from app.core.exceptions import NotFoundException


def evaluate_objective(db: Session, session_id: str, strategy: ScoringStrategy = None) -> Result:
    if strategy is None:
        strategy = AllOrNothingStrategy()

    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        raise NotFoundException("Exam session not found")

    exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
    if not exam:
        raise NotFoundException("Exam not found")

    # Fetch questions linked to exam
    exam_questions = db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).all()
    eq_map = {eq.question_id: eq for eq in exam_questions}

    # If paper generated, get order/questions
    paper_q_ids = []
    if session.generated_paper:
        for q_item in session.generated_paper:
            if isinstance(q_item, dict):
                q_id = q_item.get("question_id") or q_item.get("id")
                if q_id:
                    paper_q_ids.append(q_id)

    if not paper_q_ids:
        paper_q_ids = list(eq_map.keys())

    questions = db.query(QuestionBank).filter(QuestionBank.id.in_(paper_q_ids)).all()
    q_map = {q.id: q for q in questions}

    answers = db.query(Answer).filter(Answer.session_id == session_id).all()
    ans_map = {a.question_id: a for a in answers}

    total_marks = 0.0
    obtained_marks = 0.0
    total_negative_deductions = 0.0
    has_subjective = False
    score_breakdown: List[Dict[str, Any]] = []

    for q_id in paper_q_ids:
        q = q_map.get(q_id)
        if not q:
            continue

        eq = eq_map.get(q_id)
        max_marks = eq.marks_override if (eq and eq.marks_override is not None) else q.marks
        total_marks += max_marks

        is_objective = q.question_type in [QuestionType.MCQ, QuestionType.MULTI_SELECT]
        if not is_objective:
            has_subjective = True
            score_breakdown.append({
                "question_id": q.id,
                "question_type": q.question_type.value,
                "max_marks": max_marks,
                "obtained_marks": None,
                "status": "pending_manual_grading"
            })
            continue

        ans = ans_map.get(q.id)
        selected_ids = set(ans.selected_option_ids) if (ans and ans.selected_option_ids) else set()

        # Fetch correct options for question
        correct_opts = db.query(Option.id).filter(
            Option.question_id == q.id,
            Option.is_correct == True
        ).all()
        correct_ids = {opt[0] for opt in correct_opts}

        neg_marks = q.negative_marks if exam.negative_marking_enabled else 0.0

        q_score, q_deduction = strategy.calculate_score(
            correct_option_ids=correct_ids,
            selected_option_ids=selected_ids,
            max_marks=max_marks,
            negative_marks=neg_marks,
            negative_marking_enabled=exam.negative_marking_enabled
        )

        total_negative_deductions += q_deduction
        obtained_marks += q_score

        if ans:
            ans.marks_awarded = q_score

        score_breakdown.append({
            "question_id": q.id,
            "question_type": q.question_type.value,
            "max_marks": max_marks,
            "obtained_marks": q_score,
            "negative_deduction": q_deduction,
            "status": "auto_graded"
        })

    # Ensure obtained marks floor (never below 0 total)
    obtained_marks = max(0.0, obtained_marks)
    percentage = (obtained_marks / total_marks * 100.0) if total_marks > 0 else 0.0

    grading_status = GradingStatus.PENDING if has_subjective else GradingStatus.AUTO_GRADED

    # Upsert result
    existing_result = db.query(Result).filter(Result.session_id == session_id).first()
    now = datetime.now(timezone.utc)

    if existing_result:
        existing_result.total_marks = total_marks
        existing_result.obtained_marks = obtained_marks
        existing_result.negative_deductions = total_negative_deductions
        existing_result.percentage = percentage
        existing_result.grading_status = grading_status
        existing_result.updated_at = now
        res_record = existing_result
    else:
        res_record = Result(
            session_id=session_id,
            total_marks=total_marks,
            obtained_marks=obtained_marks,
            negative_deductions=total_negative_deductions,
            percentage=percentage,
            grading_status=grading_status,
            created_at=now,
            updated_at=now
        )
        db.add(res_record)

    db.commit()
    db.refresh(res_record)

    # Attach breakdown dynamic attribute for callers/audits
    setattr(res_record, "score_breakdown", score_breakdown)
    return res_record
