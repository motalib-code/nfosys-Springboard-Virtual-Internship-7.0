import pytest
from app.models import QuestionBank, Option, QuestionType, Difficulty, Exam, ExamQuestion, ExamSession, Answer, Result, GradingStatus
from app.services.evaluation import evaluate_objective, MCQScoringStrategy, MultiSelectScoringStrategy


def test_mcq_scoring_strategy():
    strategy = MCQScoringStrategy()
    q = QuestionBank(id="q1", question_type=QuestionType.MCQ, marks=5.0, negative_marks=1.0)
    opt_correct = Option(id="opt1", question_id="q1", is_correct=True, option_text="Correct")
    opt_wrong = Option(id="opt2", question_id="q1", is_correct=False, option_text="Wrong")
    opts = [opt_correct, opt_wrong]

    # Correct answer
    ans_correct = Answer(session_id="s1", question_id="q1", selected_option_ids=["opt1"])
    score, neg = strategy.calculate_score(q, ans_correct, 5.0, 1.0, True, opts)
    assert score == 5.0
    assert neg == 0.0

    # Wrong answer with negative marking
    ans_wrong = Answer(session_id="s1", question_id="q1", selected_option_ids=["opt2"])
    score, neg = strategy.calculate_score(q, ans_wrong, 5.0, 1.0, True, opts)
    assert score == -1.0
    assert neg == 1.0

    # Wrong answer without negative marking
    score, neg = strategy.calculate_score(q, ans_wrong, 5.0, 1.0, False, opts)
    assert score == 0.0
    assert neg == 0.0

    # Unattempted
    score, neg = strategy.calculate_score(q, None, 5.0, 1.0, True, opts)
    assert score == 0.0
    assert neg == 0.0


def test_multi_select_scoring_strategy():
    strategy = MultiSelectScoringStrategy()
    q = QuestionBank(id="q2", question_type=QuestionType.MULTI_SELECT, marks=10.0, negative_marks=2.0)
    opt1 = Option(id="opt1", question_id="q2", is_correct=True, option_text="C1")
    opt2 = Option(id="opt2", question_id="q2", is_correct=True, option_text="C2")
    opt3 = Option(id="opt3", question_id="q2", is_correct=False, option_text="W1")
    opts = [opt1, opt2, opt3]

    # Exact match -> Full marks
    ans_exact = Answer(session_id="s1", question_id="q2", selected_option_ids=["opt1", "opt2"])
    score, neg = strategy.calculate_score(q, ans_exact, 10.0, 2.0, True, opts)
    assert score == 10.0
    assert neg == 0.0

    # Partial match -> Wrong -> Negative marking
    ans_partial = Answer(session_id="s1", question_id="q2", selected_option_ids=["opt1"])
    score, neg = strategy.calculate_score(q, ans_partial, 10.0, 2.0, True, opts)
    assert score == -2.0
    assert neg == 2.0

    # Wrong selection -> Negative marking
    ans_wrong = Answer(session_id="s1", question_id="q2", selected_option_ids=["opt1", "opt3"])
    score, neg = strategy.calculate_score(q, ans_wrong, 10.0, 2.0, True, opts)
    assert score == -2.0
    assert neg == 2.0


def test_evaluate_objective_session(db_session, test_student, test_examiner):
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)

    # Create exam and questions
    q1 = QuestionBank(
        created_by=test_examiner.id,
        question_type=QuestionType.MCQ,
        subject="Math",
        difficulty=Difficulty.EASY,
        question_text="2+2?",
        marks=4.0,
        negative_marks=1.0
    )
    db_session.add(q1)
    db_session.flush()

    opt1 = Option(question_id=q1.id, option_text="4", is_correct=True)
    opt2 = Option(question_id=q1.id, option_text="5", is_correct=False)
    db_session.add_all([opt1, opt2])

    exam = Exam(
        created_by=test_examiner.id,
        title="Math Quiz",
        subject="Math",
        duration_minutes=30,
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(hours=1),
        negative_marking_enabled=True
    )
    db_session.add(exam)
    db_session.flush()

    eq = ExamQuestion(exam_id=exam.id, question_id=q1.id, order_index=0)
    db_session.add(eq)

    session = ExamSession(
        exam_id=exam.id,
        student_id=test_student.id,
        generated_paper=[{"id": q1.id, "question_type": "MCQ", "marks": 4.0}]
    )
    db_session.add(session)
    db_session.flush()

    ans = Answer(session_id=session.id, question_id=q1.id, selected_option_ids=[opt1.id])
    db_session.add(ans)
    db_session.commit()

    res = evaluate_objective(db_session, session.id)
    assert res.obtained_marks == 4.0
    assert res.total_marks == 4.0
    assert res.percentage == 100.0
    assert res.grading_status == GradingStatus.AUTO_GRADED
