from datetime import datetime, timezone, timedelta
import pytest

from app.models import (
    Exam, ExamStatus, QuestionBank, QuestionType, Difficulty,
    Option, ExamQuestion, ExamSession, SessionStatus, GradingStatus
)
from app.services.evaluation import EvaluationService, AllOrNothingScoringStrategy


def test_pure_scoring_strategy():
    strategy = AllOrNothingScoringStrategy()

    # Fake MCQ
    q_mcq = QuestionBank(question_type=QuestionType.MCQ, marks=5.0, negative_marks=1.0)
    opt_correct = Option(id="opt_c", is_correct=True)
    opt_wrong = Option(id="opt_w", is_correct=False)
    q_mcq.options = [opt_correct, opt_wrong]

    # Correct -> Full marks
    score, neg, is_corr = strategy.score_question(q_mcq, ["opt_c"], negative_marking_enabled=True)
    assert score == 5.0 and neg == 0.0 and is_corr is True

    # Wrong -> Negative marks
    score, neg, is_corr = strategy.score_question(q_mcq, ["opt_w"], negative_marking_enabled=True)
    assert score == -1.0 and neg == 1.0 and is_corr is False

    # Unattempted -> 0
    score, neg, is_corr = strategy.score_question(q_mcq, [], negative_marking_enabled=True)
    assert score == 0.0 and neg == 0.0 and is_corr is False


def test_evaluate_objective_service(client, db_session, test_examiner, test_student, student_headers):
    now = datetime.now(timezone.utc)
    exam = Exam(
        created_by=test_examiner.id,
        title="Eval Exam",
        subject="Math",
        duration_minutes=60,
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(minutes=60),
        negative_marking_enabled=True,
        status=ExamStatus.PUBLISHED
    )
    db_session.add(exam)
    db_session.commit()

    q1 = QuestionBank(created_by=test_examiner.id, question_type=QuestionType.MCQ, subject="Math", difficulty=Difficulty.EASY, question_text="q1", marks=10.0, negative_marks=2.0)
    db_session.add(q1)
    db_session.commit()

    o1 = Option(question_id=q1.id, option_text="a1", is_correct=True)
    o2 = Option(question_id=q1.id, option_text="a2", is_correct=False)
    db_session.add_all([o1, o2])
    db_session.commit()

    eq1 = ExamQuestion(exam_id=exam.id, question_id=q1.id, marks_override=12.0, order_index=1)
    db_session.add(eq1)
    db_session.commit()

    acc_res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    access_token = acc_res.json()["exam_access_token"]
    start_res = client.post(f"/api/v1/exams/{exam.id}/start", json={"exam_access_token": access_token}, headers=student_headers)
    session_id = start_res.json()["session_id"]

    # Submit correct answer
    client.put(
        f"/api/v1/sessions/{session_id}/answers/{q1.id}",
        json={"selected_option_ids": [o1.id]},
        headers=student_headers
    )

    # Submit session
    sub_res = client.post(f"/api/v1/sessions/{session_id}/submit", headers=student_headers)
    assert sub_res.status_code == 200

    result = EvaluationService.evaluate_objective(db_session, session_id)
    assert result.total_marks == 12.0  # marks_override applied
    assert result.obtained_marks == 12.0
    assert result.percentage == 100.0
    assert result.grading_status == GradingStatus.AUTO_GRADED
    assert result.score_breakdown is not None
    assert len(result.score_breakdown) == 1
