import pytest
from unittest.mock import MagicMock
from app.models import QuestionBank, QuestionType, Answer, GradingQueue, GradingAuditLog, AIEvaluation
from app.services.grading.state import GradeResult
from app.services.grading.pipeline import build_grading_graph
from app.workers.grading_worker import claim_and_process_job
from tests.test_timed_session_engine import create_published_exam

def test_langgraph_grading_pipeline_mocked(client, db_session, test_examiner, test_student, student_headers, examiner_headers):
    # Setup Exam and Short Answer Question
    exam = create_published_exam(db_session, test_examiner)

    q_short = QuestionBank(
        created_by=test_examiner.id,
        question_type=QuestionType.SHORT_ANSWER,
        subject=exam.subject,
        difficulty="medium",
        question_text="Explain database ACID properties.",
        model_answer="Atomicity, Consistency, Isolation, Durability.",
        marks=10.0
    )
    db_session.add(q_short)
    db_session.commit()

    # Create Answer record
    from app.models import ExamSession
    session = ExamSession(exam_id=exam.id, student_id=test_student.id, status="in_progress")
    db_session.add(session)
    db_session.commit()

    ans = Answer(
        session_id=session.id,
        question_id=q_short.id,
        text_answer="ACID stands for Atomicity, Consistency, Isolation, Durability."
    )
    db_session.add(ans)
    db_session.commit()
    ans_id = ans.id

    # Enqueue in GradingQueue
    queue_item = GradingQueue(
        answer_id=ans_id,
        session_id=session.id,
        exam_id=exam.id,
        status="pending"
    )
    db_session.add(queue_item)
    db_session.commit()

    # Mock LLM Structured Output
    mock_llm = MagicMock()
    mock_grade = GradeResult(
        suggested_score=9.5,
        max_score=10.0,
        justification="Accurate explanation of all ACID components.",
        key_points_matched=["Atomicity", "Consistency", "Isolation", "Durability"],
        key_points_missed=[],
        confidence=0.98
    )
    mock_llm.invoke.return_value = mock_grade

    # Run claim and process job
    from unittest.mock import patch
    with patch("app.workers.grading_worker.SessionLocal", return_value=db_session), \
         patch("app.services.grading.pipeline.SessionLocal", return_value=db_session):
        claimed = claim_and_process_job(llm_client=mock_llm)
        assert claimed is True

    # Verify AI evaluation persisted
    ai_eval = db_session.query(AIEvaluation).filter(AIEvaluation.answer_id == ans_id).first()
    assert ai_eval is not None
    assert ai_eval.suggested_score == 9.5
    assert ai_eval.confidence == 0.98

    # Verify examiner can inspect details via GET /grading/answers/{id}
    res_detail = client.get(f"/api/v1/grading/answers/{ans_id}", headers=examiner_headers)
    assert res_detail.status_code == 200
    assert res_detail.json()["ai_suggestion"]["suggested_score"] == 9.5

    # Examiner finalizes manual grade via PUT /grading/answers/{id}
    put_res = client.put(
        f"/api/v1/grading/answers/{ans_id}?marks_awarded=10.0&feedback=Perfect",
        headers=examiner_headers
    )
    assert put_res.status_code == 200
    assert put_res.json()["marks_awarded"] == 10.0

    # Verify audit log recorded
    audit = db_session.query(GradingAuditLog).filter(GradingAuditLog.answer_id == ans_id).first()
    assert audit is not None
    assert audit.new_score == 10.0
    assert audit.note == "Perfect"
