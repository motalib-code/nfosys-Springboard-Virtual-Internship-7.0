from abc import ABC, abstractmethod
from typing import List, Set, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models import (
    QuestionBank, Option, Answer, ExamQuestion, QuestionType, Result, GradingStatus,
    ExamSession, Exam, GradingQueue, GradingQueueStatus
)


class ScoringStrategy(ABC):
    @abstractmethod
    def calculate_score(
        self,
        question: QuestionBank,
        answer: Optional[Answer],
        marks: float,
        negative_marks: float,
        negative_marking_enabled: bool,
        options: List[Option]
    ) -> tuple[float, float]:
        """Returns (obtained_marks, negative_deduction)."""
        pass


class MCQScoringStrategy(ScoringStrategy):
    def calculate_score(
        self,
        question: QuestionBank,
        answer: Optional[Answer],
        marks: float,
        negative_marks: float,
        negative_marking_enabled: bool,
        options: List[Option]
    ) -> tuple[float, float]:
        if not answer or not answer.selected_option_ids:
            return 0.0, 0.0

        selected = answer.selected_option_ids
        if isinstance(selected, list):
            selected_id = selected[0] if selected else None
        else:
            selected_id = str(selected)

        if not selected_id:
            return 0.0, 0.0

        correct_option = next((opt for opt in options if opt.is_correct), None)
        if correct_option and selected_id == correct_option.id:
            return marks, 0.0

        # Wrong answer
        deduction = negative_marks if negative_marking_enabled else 0.0
        return -deduction, deduction


class MultiSelectScoringStrategy(ScoringStrategy):
    """
    Documented Multi-Select Scoring Strategy: All-or-Nothing Rule.
    - Correct Set Exact Match: Student selected EXACTLY all correct option IDs (and no extra options) -> Full Marks.
    - Any Wrong or Partial/Incorrect Set:
        * If attempted and negative marking is enabled -> Deduct negative_marks.
        * Otherwise -> 0 marks.
    - Unattempted (no options selected) -> 0 marks, 0 deduction.
    """
    def calculate_score(
        self,
        question: QuestionBank,
        answer: Optional[Answer],
        marks: float,
        negative_marks: float,
        negative_marking_enabled: bool,
        options: List[Option]
    ) -> tuple[float, float]:
        if not answer or not answer.selected_option_ids:
            return 0.0, 0.0

        selected_set = set(answer.selected_option_ids)
        if not selected_set:
            return 0.0, 0.0

        correct_set = {opt.id for opt in options if opt.is_correct}

        if selected_set == correct_set:
            return marks, 0.0

        # Wrong or partial
        deduction = negative_marks if negative_marking_enabled else 0.0
        return -deduction, deduction


class ObjectiveEvaluator:
    strategies: Dict[QuestionType, ScoringStrategy] = {
        QuestionType.MCQ: MCQScoringStrategy(),
        QuestionType.MULTI_SELECT: MultiSelectScoringStrategy(),
    }

    @classmethod
    def evaluate_objective(cls, db: Session, session_id: str) -> Result:
        """
        Evaluates objective questions for an exam session in ONE short transaction.
        Updates answer marks, aggregates results into Result, and sets grading status.
        Also enqueues subjective answers into GradingQueue.
        """
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
        if not exam:
            raise ValueError(f"Exam {session.exam_id} not found")

        # Get generated paper or exam questions
        paper_questions = session.generated_paper or []
        if not paper_questions:
            from app.services.paper_generator import PaperGenerator
            paper_data = PaperGenerator.generate_paper(db, exam, session.student_id)
            session.paper_seed = paper_data["seed"]
            session.generated_paper = paper_data["questions"]
            paper_questions = session.generated_paper

        q_ids = [q.get("question_id") or q.get("id") for q in paper_questions]

        # Fetch questions, options, overrides, and student answers
        questions = db.query(QuestionBank).filter(QuestionBank.id.in_(q_ids)).all()
        q_map = {q.id: q for q in questions}

        exam_questions = db.query(ExamQuestion).filter(
            ExamQuestion.exam_id == exam.id,
            ExamQuestion.question_id.in_(q_ids)
        ).all()
        override_map = {eq.question_id: eq.marks_override for eq in exam_questions}

        answers = db.query(Answer).filter(Answer.session_id == session_id).all()
        answer_map = {ans.question_id: ans for ans in answers}

        total_marks = 0.0
        obtained_marks = 0.0
        negative_deductions = 0.0
        has_subjective = False
        score_breakdown = []

        for q_entry in paper_questions:
            q_id = q_entry.get("question_id") or q_entry.get("id")
            q_db = q_map.get(q_id)
            if not q_db:
                continue

            marks = override_map.get(q_id) if override_map.get(q_id) is not None else q_db.marks
            neg_marks = q_db.negative_marks if exam.negative_marking_enabled else 0.0

            total_marks += marks
            ans = answer_map.get(q_id)

            if q_db.question_type in [QuestionType.MCQ, QuestionType.MULTI_SELECT]:
                strategy = cls.strategies.get(q_db.question_type)
                opts = list(q_db.options)
                score, deduction = strategy.calculate_score(
                    q_db, ans, marks, neg_marks, exam.negative_marking_enabled, opts
                )

                if ans:
                    ans.marks_awarded = score

                obtained_marks += score
                negative_deductions += deduction

                score_breakdown.append({
                    "question_id": q_id,
                    "question_type": q_db.question_type.value,
                    "max_marks": marks,
                    "obtained_marks": score,
                    "negative_deduction": deduction,
                    "is_subjective": False
                })
            else:
                has_subjective = True
                awarded = ans.marks_awarded if (ans and ans.marks_awarded is not None) else 0.0
                obtained_marks += awarded
                score_breakdown.append({
                    "question_id": q_id,
                    "question_type": q_db.question_type.value,
                    "max_marks": marks,
                    "obtained_marks": awarded,
                    "negative_deduction": 0.0,
                    "is_subjective": True
                })

                if ans:
                    existing_queue = db.query(GradingQueue).filter(GradingQueue.answer_id == ans.id).first()
                    if not existing_queue:
                        q_item = GradingQueue(
                            answer_id=ans.id,
                            session_id=session_id,
                            exam_id=exam.id,
                            status=GradingQueueStatus.PENDING,
                            priority=1 if q_db.question_type == QuestionType.IMAGE_UPLOAD else 0
                        )
                        db.add(q_item)

        # Never let obtained marks go below 0 (configured floor)
        final_obtained_marks = max(0.0, obtained_marks)
        percentage = (final_obtained_marks / total_marks * 100.0) if total_marks > 0 else 0.0

        grading_status = GradingStatus.PENDING if has_subjective else GradingStatus.AUTO_GRADED

        existing_result = db.query(Result).filter(Result.session_id == session_id).first()
        if existing_result:
            existing_result.total_marks = total_marks
            existing_result.obtained_marks = final_obtained_marks
            existing_result.negative_deductions = negative_deductions
            existing_result.percentage = round(percentage, 2)
            existing_result.score_breakdown = score_breakdown
            existing_result.grading_status = grading_status
            result_obj = existing_result
        else:
            result_obj = Result(
                session_id=session_id,
                total_marks=total_marks,
                obtained_marks=final_obtained_marks,
                negative_deductions=negative_deductions,
                percentage=round(percentage, 2),
                score_breakdown=score_breakdown,
                grading_status=grading_status
            )
            db.add(result_obj)

        db.commit()
        db.refresh(result_obj)
        return result_obj


def evaluate_objective(db: Session, session_id: str) -> Result:
    return ObjectiveEvaluator.evaluate_objective(db, session_id)
