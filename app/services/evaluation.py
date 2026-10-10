import abc
import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session, joinedload
from app.models import (
    ExamSession, Exam, ExamQuestion, QuestionBank, Answer, Result,
    QuestionType, GradingStatus
)

logger = logging.getLogger(__name__)


class ScoringStrategy(abc.ABC):
    @abc.abstractmethod
    def score_question(
        self,
        question: QuestionBank,
        selected_option_ids: Optional[List[str]],
        marks_override: Optional[float] = None,
        negative_marking_enabled: bool = False
    ) -> Tuple[float, float, bool]:
        """
        Returns (marks_awarded, negative_deduction, is_correct)
        """
        pass


class AllOrNothingScoringStrategy(ScoringStrategy):
    def score_question(
        self,
        question: QuestionBank,
        selected_option_ids: Optional[List[str]],
        marks_override: Optional[float] = None,
        negative_marking_enabled: bool = False
    ) -> Tuple[float, float, bool]:
        max_marks = marks_override if marks_override is not None else question.marks
        neg_marks = question.negative_marks if negative_marking_enabled else 0.0

        if not selected_option_ids:
            return 0.0, 0.0, False

        correct_option_ids = {opt.id for opt in question.options if opt.is_correct}
        selected_set = set(selected_option_ids)

        if question.question_type == QuestionType.MCQ:
            if len(selected_option_ids) == 1 and selected_option_ids[0] in correct_option_ids:
                return max_marks, 0.0, True
            else:
                return -neg_marks if negative_marking_enabled else 0.0, neg_marks if negative_marking_enabled else 0.0, False

        elif question.question_type == QuestionType.MULTI_SELECT:
            if selected_set == correct_option_ids and len(correct_option_ids) > 0:
                return max_marks, 0.0, True
            else:
                return -neg_marks if negative_marking_enabled else 0.0, neg_marks if negative_marking_enabled else 0.0, False

        return 0.0, 0.0, False


class EvaluationService:
    @staticmethod
    def evaluate_objective(
        db: Session,
        session_id: str,
        strategy: Optional[ScoringStrategy] = None
    ) -> Result:
        if strategy is None:
            strategy = AllOrNothingScoringStrategy()

        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise ValueError(f"Exam session {session_id} not found")

        exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
        if not exam:
            raise ValueError(f"Exam {session.exam_id} not found")

        eq_map = {}
        exam_questions = db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).all()
        for eq in exam_questions:
            eq_map[eq.question_id] = eq.marks_override

        paper_questions = session.generated_paper or []
        answers_map = {ans.question_id: ans for ans in db.query(Answer).filter(Answer.session_id == session_id).all()}

        total_marks = 0.0
        raw_obtained_marks = 0.0
        total_negative_deductions = 0.0
        has_subjective = False
        score_breakdown = []

        for pq in paper_questions:
            q_id = pq.get("question_id") or pq.get("id")
            question = db.query(QuestionBank).options(joinedload(QuestionBank.options)).filter(QuestionBank.id == q_id).first()
            if not question:
                continue

            marks_override = eq_map.get(q_id)
            max_marks = marks_override if marks_override is not None else question.marks
            total_marks += max_marks

            ans = answers_map.get(q_id)
            selected_opts = ans.selected_option_ids if ans else None

            if question.question_type in [QuestionType.MCQ, QuestionType.MULTI_SELECT]:
                awarded, neg_ded, is_corr = strategy.score_question(
                    question,
                    selected_opts,
                    marks_override=marks_override,
                    negative_marking_enabled=exam.negative_marking_enabled
                )
                raw_obtained_marks += awarded
                total_negative_deductions += neg_ded

                if ans:
                    ans.marks_awarded = awarded

                score_breakdown.append({
                    "question_id": q_id,
                    "question_type": question.question_type.value,
                    "max_marks": max_marks,
                    "selected_option_ids": selected_opts,
                    "marks_awarded": awarded,
                    "negative_deduction": neg_ded,
                    "is_correct": is_corr
                })
            else:
                has_subjective = True
                awarded = ans.marks_awarded if (ans and ans.marks_awarded is not None) else None
                if awarded is not None:
                    raw_obtained_marks += awarded

                score_breakdown.append({
                    "question_id": q_id,
                    "question_type": question.question_type.value,
                    "max_marks": max_marks,
                    "text_answer": ans.text_answer if ans else None,
                    "image_answer_url": ans.image_answer_url if ans else None,
                    "marks_awarded": awarded,
                    "status": "manually_graded" if awarded is not None else "pending_manual_grading"
                })

        obtained_marks = max(0.0, raw_obtained_marks)
        percentage = (obtained_marks / total_marks * 100.0) if total_marks > 0 else 0.0
        grading_status = GradingStatus.PENDING if has_subjective else GradingStatus.AUTO_GRADED

        now = datetime.now(timezone.utc)
        result = db.query(Result).filter(Result.session_id == session_id).first()
        if result:
            result.total_marks = total_marks
            result.obtained_marks = obtained_marks
            result.negative_deductions = total_negative_deductions
            result.percentage = percentage
            result.grading_status = grading_status
            result.score_breakdown = score_breakdown
            result.updated_at = now
        else:
            result = Result(
                session_id=session_id,
                total_marks=total_marks,
                obtained_marks=obtained_marks,
                negative_deductions=total_negative_deductions,
                percentage=percentage,
                grading_status=grading_status,
                score_breakdown=score_breakdown,
                created_at=now,
                updated_at=now
            )
            db.add(result)

        db.commit()
        db.refresh(result)
        return result
