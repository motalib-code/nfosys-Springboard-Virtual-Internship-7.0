from datetime import datetime, timezone, timedelta
import pytest
from app.models import Exam, ExamStatus, ExamSession, SessionStatus, SubmittedReason, ProctorEvent, ProctorEventType
from app.services.scheduler import sweep_expired_sessions, auto_submit_session_job


def create_published_exam(db, examiner, duration_minutes=30, window_minutes=60):
    now = datetime.now(timezone.utc)
    exam = Exam(
        created_by=examiner.id,
        title="Timed Engine Exam",
        subject="Computer Science",
        duration_minutes=duration_minutes,
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(minutes=window_minutes),
        status=ExamStatus.PUBLISHED
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def test_server_deadline_computation(client, db_session, test_examiner, test_student, student_headers):
    # Exam 1: duration_minutes=30, end_time in 60 minutes -> server_deadline = started_at + 30m
    exam1 = create_published_exam(db_session, test_examiner, duration_minutes=30, window_minutes=60)

    # Issue access token
    res = client.post(f"/api/v1/exams/{exam1.id}/access-token", headers=student_headers)
    assert res.status_code == 200
    access_token = res.json()["exam_access_token"]

    # Start exam
    start_res = client.post(
        f"/api/v1/exams/{exam1.id}/start",
        json={"exam_access_token": access_token},
        headers=student_headers
    )
    assert start_res.status_code == 200
    session_id = start_res.json()["session_id"]

    session = db_session.query(ExamSession).filter(ExamSession.id == session_id).first()
    assert session is not None
    assert session.started_at is not None
    assert session.server_deadline is not None

    # Verify deadline is min(started_at + 30m, end_time)
    expected_deadline = session.started_at.replace(tzinfo=timezone.utc) + timedelta(minutes=30)
    diff = abs((session.server_deadline.replace(tzinfo=timezone.utc) - expected_deadline).total_seconds())
    assert diff < 2

    # Exam 2: duration_minutes=60, end_time in 10 minutes -> server_deadline = exam.end_time
    exam2 = create_published_exam(db_session, test_examiner, duration_minutes=60, window_minutes=10)

    res2 = client.post(f"/api/v1/exams/{exam2.id}/access-token", headers=student_headers)
    access_token2 = res2.json()["exam_access_token"]

    start_res2 = client.post(
        f"/api/v1/exams/{exam2.id}/start",
        json={"exam_access_token": access_token2},
        headers=student_headers
    )
    assert start_res2.status_code == 200
    session_id2 = start_res2.json()["session_id"]

    session2 = db_session.query(ExamSession).filter(ExamSession.id == session_id2).first()
    assert session2 is not None
    exam2_end = exam2.end_time.replace(tzinfo=timezone.utc) if exam2.end_time.tzinfo is None else exam2.end_time
    deadline2 = session2.server_deadline.replace(tzinfo=timezone.utc) if session2.server_deadline.tzinfo is None else session2.server_deadline
    diff2 = abs((deadline2 - exam2_end).total_seconds())
    assert diff2 < 2


def test_time_remaining_endpoint(client, db_session, test_examiner, test_student, student_headers):
    exam = create_published_exam(db_session, test_examiner, duration_minutes=30, window_minutes=60)

    res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    access_token = res.json()["exam_access_token"]

    start_res = client.post(
        f"/api/v1/exams/{exam.id}/start",
        json={"exam_access_token": access_token},
        headers=student_headers
    )
    session_id = start_res.json()["session_id"]

    # Call GET /sessions/{id}/time-remaining
    tr_res = client.get(f"/api/v1/sessions/{session_id}/time-remaining", headers=student_headers)
    assert tr_res.status_code == 200
    data = tr_res.json()

    assert data["session_id"] == session_id
    assert 1700 <= data["seconds_remaining"] <= 1800
    assert data["status"] == "in_progress"
    assert "server_time" in data
    assert "server_deadline" in data


def test_grace_window_and_deadline_rejection(client, db_session, test_examiner, test_student, student_headers):
    exam = create_published_exam(db_session, test_examiner, duration_minutes=30, window_minutes=60)

    res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    access_token = res.json()["exam_access_token"]

    start_res = client.post(
        f"/api/v1/exams/{exam.id}/start",
        json={"exam_access_token": access_token},
        headers=student_headers
    )
    session_id = start_res.json()["session_id"]
    session_token = start_res.json()["session_token"]

    # Manually expire server_deadline (10 seconds ago)
    session = db_session.query(ExamSession).filter(ExamSession.id == session_id).first()
    session.server_deadline = datetime.now(timezone.utc) - timedelta(seconds=10)
    db_session.commit()

    # Attempt answer submission past grace window
    answer_res = client.post(
        f"/api/v1/sessions/{session_id}/answers",
        json={"question_id": "dummy_q_id", "text_answer": "My answer"},
        headers={"Authorization": f"Bearer {session_token}"}
    )
    assert answer_res.status_code == 409
    assert "auto-submitted" in answer_res.json()["detail"].lower()

    # Verify session is now auto_submitted and submitted_reason = time_expired
    db_session.refresh(session)
    assert session.status == SessionStatus.AUTO_SUBMITTED
    assert session.submitted_reason == SubmittedReason.TIME_EXPIRED


def test_idempotent_auto_submit_sweeper(client, db_session, test_examiner, test_student, student_headers):
    exam = create_published_exam(db_session, test_examiner, duration_minutes=30, window_minutes=60)

    res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    access_token = res.json()["exam_access_token"]

    start_res = client.post(
        f"/api/v1/exams/{exam.id}/start",
        json={"exam_access_token": access_token},
        headers=student_headers
    )
    session_id = start_res.json()["session_id"]

    # Set deadline in the past
    session = db_session.query(ExamSession).filter(ExamSession.id == session_id).first()
    session.server_deadline = datetime.now(timezone.utc) - timedelta(seconds=20)
    db_session.commit()

    # Trigger sweeper
    sweep_expired_sessions(db_session=db_session)

    db_session.refresh(session)
    assert session.status == SessionStatus.AUTO_SUBMITTED
    assert session.submitted_reason == SubmittedReason.TIME_EXPIRED

    # Trigger job directly to test idempotency
    auto_submit_session_job(session_id, db_session=db_session)
    db_session.refresh(session)
    assert session.status == SessionStatus.AUTO_SUBMITTED


def test_single_active_session_and_token_rotation(client, db_session, test_examiner, test_student, student_headers):
    exam = create_published_exam(db_session, test_examiner, duration_minutes=30, window_minutes=60)

    # First start
    res1 = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    token1 = res1.json()["exam_access_token"]
    start1 = client.post(f"/api/v1/exams/{exam.id}/start", json={"exam_access_token": token1}, headers=student_headers)
    session_id = start1.json()["session_id"]
    session_token1 = start1.json()["session_token"]

    # Second start attempt (session takeover / concurrent login)
    res2 = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    token2 = res2.json()["exam_access_token"]
    start2 = client.post(f"/api/v1/exams/{exam.id}/start", json={"exam_access_token": token2}, headers=student_headers)
    assert start2.status_code == 200
    session_token2 = start2.json()["session_token"]
    assert session_token1 != session_token2

    # Old token fails heartbeat due to JTI rotation
    hb1 = client.post(f"/api/v1/sessions/{session_id}/heartbeat", headers={"Authorization": f"Bearer {session_token1}"})
    assert hb1.status_code == 401

    # New token succeeds heartbeat
    hb2 = client.post(f"/api/v1/sessions/{session_id}/heartbeat", headers={"Authorization": f"Bearer {session_token2}"})
    assert hb2.status_code == 200

    # Verify proctor event was recorded for rotation
    proctor_events = db_session.query(ProctorEvent).filter(ProctorEvent.session_id == session_id).all()
    assert len(proctor_events) >= 1
