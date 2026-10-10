import pytest
from app.models import QuestionBank, QuestionType, Option, ExamQuestion, GradingStatus, Answer
from app.services.scoring_strategies import AllOrNothingStrategy, PartialCreditStrategy
from app.services.evaluator import evaluate_objective
from tests.test_timed_session_engine import create_published_exam

def test_pure_scoring_strategy_unit():
    strategy = AllOrNothingStrategy()
    correct = {"opt1", "opt2"}

    # 1. Full match
    score, ded = strategy.calculate_score(correct, {"opt1", "opt2"}, max_marks=4.0, negative_marks=1.0, negative_marking_enabled=True)
    assert score == 4.0 and ded == 0.0

    # 2. Unattempted
    score, ded = strategy.calculate_score(correct, set(), max_marks=4.0, negative_marks=1.0, negative_marking_enabled=True)
    assert score == 0.0 and ded == 0.0

    # 3. Wrong selection with negative marking
    score, ded = strategy.calculate_score(correct, {"opt1", "opt3"}, max_marks=4.0, negative_marks=1.0, negative_marking_enabled=True)
    assert score == -1.0 and ded == 1.0

    # 4. Wrong selection without negative marking
    score, ded = strategy.calculate_score(correct, {"opt1", "opt3"}, max_marks=4.0, negative_marks=1.0, negative_marking_enabled=False)
    assert score == 0.0 and ded == 0.0


def test_evaluate_objective_integration(client, db_session, test_examiner, test_student, student_headers):
    # Setup Exam
    exam = create_published_exam(db_session, test_examiner)
    exam.negative_marking_enabled = True

    # Question 1: MCQ (2 marks, 0.5 neg)
    q1 = QuestionBank(
        created_by=test_examiner.id,
        question_type=QuestionType.MCQ,
        subject=exam.subject,
        difficulty="easy",
        question_text="Q1",
        marks=2.0,
        negative_marks=0.5
    )
    db_session.add(q1)
    db_session.flush()

    o1_1 = Option(question_id=q1.id, option_text="A", is_correct=True)
    o1_2 = Option(question_id=q1.id, option_text="B", is_correct=False)
    db_session.add_all([o1_1, o1_2])

    # Question 2: Short Answer (subjective, 5 marks)
    q2 = QuestionBank(
        created_by=test_examiner.id,
        question_type=QuestionType.SHORT_ANSWER,
        subject=exam.subject,
        difficulty="easy",
        question_text="Q2",
        marks=5.0
    )
    db_session.add(q2)
    db_session.commit()

    eq1 = ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0)
    eq2 = ExamQuestion(exam_id=exam.id, question_id=q2.id, order_index=1)
    db_session.add_all([eq1, eq2])
    db_session.commit()

    # Start session
    res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    token = res.json()["exam_access_token"]
    start_res = client.post(f"/api/v1/exams/{exam.id}/start", json={"exam_access_token": token}, headers=student_headers)
    session_id = start_res.json()["session_id"]

    # Submit correct answer for Q1
    client.put(
        f"/api/v1/sessions/{session_id}/answers/{q1.id}",
        json={"question_id": q1.id, "selected_option_ids": [o1_1.id]},
        headers=student_headers
    )

    # Evaluate objective
    result = evaluate_objective(db_session, session_id)
    assert result.total_marks == 7.0
    assert result.obtained_marks == 2.0
    assert result.grading_status == GradingStatus.PENDING  # Pending because q2 is subjective
