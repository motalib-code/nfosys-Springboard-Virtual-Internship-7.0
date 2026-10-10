from datetime import datetime, timezone, timedelta
import pytest

from app.models import (
    Exam, ExamStatus, ProctorEvent, ProctorEventType, ExamSession, UserRole
)
from app.services.suspicion_scorer import calculate_suspicion_score


def test_suspicion_scorer_pure_function():
    now = datetime.now(timezone.utc)
    ev1 = ProctorEvent(event_type=ProctorEventType.MULTIPLE_FACES, timestamp=now)
    ev2 = ProctorEvent(event_type=ProctorEventType.TAB_SWITCH, timestamp=now)

    score = calculate_suspicion_score([ev1, ev2], now=now)
    assert score == 35.0  # 25 + 10 = 35

    # Old event (> 10m ago) should decay
    ev_old = ProctorEvent(event_type=ProctorEventType.NO_FACE, timestamp=now - timedelta(minutes=15))
    score_decayed = calculate_suspicion_score([ev_old], now=now)
    assert score_decayed < 15.0


def test_proctor_precheck_endpoint(client, db_session, test_examiner, test_student, student_headers):
    now = datetime.now(timezone.utc)
    exam = Exam(
        created_by=test_examiner.id,
        title="Precheck Exam",
        subject="Proctoring",
        duration_minutes=60,
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(minutes=60),
        status=ExamStatus.PUBLISHED
    )
    db_session.add(exam)
    db_session.commit()

    acc_res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    access_token = acc_res.json()["exam_access_token"]
    start_res = client.post(f"/api/v1/exams/{exam.id}/start", json={"exam_access_token": access_token}, headers=student_headers)
    session_id = start_res.json()["session_id"]

    # Precheck fails when no face present
    fail_res = client.post(
        f"/api/v1/sessions/{session_id}/proctor/precheck",
        json={"face_present": False, "face_count": 0},
        headers=student_headers
    )
    assert fail_res.status_code == 400

    # Precheck passes when face present
    pass_res = client.post(
        f"/api/v1/sessions/{session_id}/proctor/precheck",
        json={"face_present": True, "face_count": 1},
        headers=student_headers
    )
    assert pass_res.status_code == 200
    assert pass_res.json()["success"] is True


def test_examiner_proctoring_sessions_report(client, db_session, test_examiner, examiner_headers, test_student, student_headers):
    now = datetime.now(timezone.utc)
    exam = Exam(
        created_by=test_examiner.id,
        title="Report Exam",
        subject="Proctoring",
        duration_minutes=60,
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(minutes=60),
        status=ExamStatus.PUBLISHED
    )
    db_session.add(exam)
    db_session.commit()

    acc_res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    access_token = acc_res.json()["exam_access_token"]
    client.post(f"/api/v1/exams/{exam.id}/start", json={"exam_access_token": access_token}, headers=student_headers)

    res = client.get(f"/api/v1/exams/{exam.id}/proctoring/sessions", headers=examiner_headers)
    assert res.status_code == 200
    data = res.json()
    assert "sessions" in data
    assert len(data["sessions"]) == 1
