from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Sequence

from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.db.session import engine
from app.models import (
    Answer,
    ExamQuestion,
    ExamSession,
    GradingStatus,
    Option,
    QuestionType,
    Result,
    ResultItem,
)


SUBJECTIVE_TYPES = {
    QuestionType.SHORT_ANSWER,
    QuestionType.LONG_ANSWER,
    QuestionType.IMAGE_UPLOAD,
}


@dataclass(slots=True)
class ScoreOutcome:
    marks_awarded: float
    negative_deduction: float
    strategy: str
    details: Dict[str, Any]


class MultiSelectScoringStrategy:
    name = "base"

    def score(
        self,
        selected_option_ids: Sequence[str],
        correct_option_ids: Sequence[str],
        full_marks: float,
        negative_marks: float,
        negative_enabled: bool,
    ) -> ScoreOutcome:
        raise NotImplementedError


class AllOrNothingMultiSelectScoring(MultiSelectScoringStrategy):
    name = "all_or_nothing"

    def score(
        self,
        selected_option_ids: Sequence[str],
        correct_option_ids: Sequence[str],
        full_marks: float,
        negative_marks: float,
        negative_enabled: bool,
    ) -> ScoreOutcome:
        selected_set = set(selected_option_ids)
        correct_set = set(correct_option_ids)
        attempted = len(selected_set) > 0
        is_exact_match = attempted and selected_set == correct_set

        if is_exact_match:
            return ScoreOutcome(
                marks_awarded=full_marks,
                negative_deduction=0.0,
                strategy=self.name,
                details={"rule": "exact_set_match", "is_exact_match": True},
            )

        deduction = negative_marks if negative_enabled and attempted else 0.0
        return ScoreOutcome(
            marks_awarded=-deduction,
            negative_deduction=deduction,
            strategy=self.name,
            details={"rule": "exact_set_match", "is_exact_match": False},
        )


class ObjectiveEvaluationService:
    @staticmethod
    def _select_multi_select_strategy() -> MultiSelectScoringStrategy:
        strategy = settings.MULTI_SELECT_SCORING_STRATEGY.strip().lower()
        if strategy == "all_or_nothing":
            return AllOrNothingMultiSelectScoring()
        return AllOrNothingMultiSelectScoring()

    @staticmethod
    def _dedupe_ids(value: Iterable[str] | None) -> list[str]:
        if not value:
            return []
        seen: set[str] = set()
        output: list[str] = []
        for option_id in value:
            if option_id not in seen:
                seen.add(option_id)
                output.append(option_id)
        return output

    @staticmethod
    def _score_mcq(
        answer: Answer | None,
        correct_option_ids: Sequence[str],
        full_marks: float,
        negative_marks: float,
        negative_enabled: bool,
    ) -> ScoreOutcome:
        selected = ObjectiveEvaluationService._dedupe_ids(answer.selected_option_ids if answer else None)
        attempted = len(selected) > 0
        is_correct = attempted and len(selected) == 1 and selected[0] in set(correct_option_ids)

        if is_correct:
            return ScoreOutcome(
                marks_awarded=full_marks,
                negative_deduction=0.0,
                strategy="mcq_single_correct",
                details={"is_correct": True},
            )

        deduction = negative_marks if negative_enabled and attempted else 0.0
        return ScoreOutcome(
            marks_awarded=-deduction,
            negative_deduction=deduction,
            strategy="mcq_single_correct",
            details={"is_correct": False, "attempted": attempted},
        )

    @staticmethod
    def evaluate_objective(db: Session, session_id: str) -> Result:
        query = (
            db.query(ExamSession)
            .filter(ExamSession.id == session_id)
            .options(joinedload(ExamSession.exam), joinedload(ExamSession.answers))
        )
        if engine.dialect.name != "sqlite":
            query = query.with_for_update()
        session = query.first()
        if not session:
            raise NotFoundException("Exam session not found")

        exam = session.exam
        exam_question_rows = (
            db.query(ExamQuestion)
            .filter(ExamQuestion.exam_id == session.exam_id)
            .options(joinedload(ExamQuestion.question).joinedload("options"))
            .all()
        )

        question_by_id = {row.question_id: row for row in exam_question_rows}
        answer_by_question = {a.question_id: a for a in session.answers}
        multi_select_strategy = ObjectiveEvaluationService._select_multi_select_strategy()

        total_marks = 0.0
        obtained_marks = 0.0
        negative_deductions = 0.0
        result_items: list[ResultItem] = []
        has_subjective = False

        for question_id, exam_question in question_by_id.items():
            question = exam_question.question
            max_marks = exam_question.marks_override if exam_question.marks_override is not None else question.marks
            total_marks += max_marks

            answer = answer_by_question.get(question_id)

            if question.question_type in SUBJECTIVE_TYPES:
                has_subjective = True
                marks_awarded = answer.marks_awarded if answer and answer.marks_awarded is not None else 0.0
                if answer:
                    answer.marks_awarded = marks_awarded
                result_items.append(
                    ResultItem(
                        result_id="",
                        session_id=session.id,
                        question_id=question_id,
                        question_type=question.question_type,
                        max_marks=max_marks,
                        marks_awarded=marks_awarded,
                        negative_deduction=0.0,
                        scoring_strategy="subjective_pending",
                        scoring_details={"state": "pending_manual_evaluation"},
                    )
                )
                obtained_marks += marks_awarded
                continue

            correct_option_ids = [opt.id for opt in question.options if opt.is_correct]
            if question.question_type == QuestionType.MCQ:
                outcome = ObjectiveEvaluationService._score_mcq(
                    answer=answer,
                    correct_option_ids=correct_option_ids,
                    full_marks=max_marks,
                    negative_marks=question.negative_marks,
                    negative_enabled=exam.negative_marking_enabled,
                )
            elif question.question_type == QuestionType.MULTI_SELECT:
                selected = ObjectiveEvaluationService._dedupe_ids(answer.selected_option_ids if answer else None)
                outcome = multi_select_strategy.score(
                    selected_option_ids=selected,
                    correct_option_ids=correct_option_ids,
                    full_marks=max_marks,
                    negative_marks=question.negative_marks,
                    negative_enabled=exam.negative_marking_enabled,
                )
            else:
                outcome = ScoreOutcome(
                    marks_awarded=0.0,
                    negative_deduction=0.0,
                    strategy="unsupported_objective_type",
                    details={"question_type": question.question_type.value},
                )

            if answer:
                answer.marks_awarded = outcome.marks_awarded
                answer.graded_at = datetime.now(timezone.utc)

            obtained_marks += outcome.marks_awarded
            negative_deductions += outcome.negative_deduction
            result_items.append(
                ResultItem(
                    result_id="",
                    session_id=session.id,
                    question_id=question_id,
                    question_type=question.question_type,
                    max_marks=max_marks,
                    marks_awarded=outcome.marks_awarded,
                    negative_deduction=outcome.negative_deduction,
                    scoring_strategy=outcome.strategy,
                    scoring_details=outcome.details,
                )
            )

        obtained_marks = max(settings.EXAM_OBTAINED_MARKS_FLOOR, obtained_marks)
        percentage = (obtained_marks / total_marks * 100.0) if total_marks > 0 else 0.0

        result = db.query(Result).filter(Result.session_id == session.id).first()
        if not result:
            result = Result(
                session_id=session.id,
                total_marks=total_marks,
                obtained_marks=obtained_marks,
                negative_deductions=negative_deductions,
                percentage=percentage,
                grading_status=GradingStatus.PENDING if has_subjective else GradingStatus.AUTO_GRADED,
            )
            db.add(result)
            db.flush()
        else:
            result.total_marks = total_marks
            result.obtained_marks = obtained_marks
            result.negative_deductions = negative_deductions
            result.percentage = percentage
            result.grading_status = GradingStatus.PENDING if has_subjective else GradingStatus.AUTO_GRADED
            db.query(ResultItem).filter(ResultItem.result_id == result.id).delete()

        for item in result_items:
            item.result_id = result.id
            db.add(item)

        db.flush()
        db.refresh(result)
        return result
