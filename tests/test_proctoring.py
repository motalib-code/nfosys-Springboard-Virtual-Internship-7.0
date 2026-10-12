import pytest
from app.services.suspicion_scorer import calculate_suspicion_score, DEFAULT_WEIGHTS
from app.models import ProctorEventType


def test_suspicion_scorer_purity_and_caps():
    # Empty events
    assert calculate_suspicion_score([]) == 0.0

    # Monotonicity and severity weighting
    events_low = [{"event_type": ProctorEventType.NO_FACE, "severity": "warning"}]
    events_high = [{"event_type": ProctorEventType.NO_FACE, "severity": "high"}]

    score_low = calculate_suspicion_score(events_low)
    score_high = calculate_suspicion_score(events_high)

    assert score_high > score_low

    # Capped at 100
    many_events = [{"event_type": ProctorEventType.CONCURRENT_SESSION, "severity": "critical"} for _ in range(20)]
    assert calculate_suspicion_score(many_events) <= 100.0


def test_suspicion_scorer_disabled_settings():
    events = [
        {"event_type": ProctorEventType.NO_FACE, "severity": "warning"},
        {"event_type": ProctorEventType.GAZE_AWAY, "severity": "warning"}
    ]

    # Enabled
    score_enabled = calculate_suspicion_score(events, proctoring_settings={"webcam_enabled": True, "gaze_enabled": True})
    assert score_enabled > 0.0

    # Disabled
    score_disabled = calculate_suspicion_score(events, proctoring_settings={"webcam_enabled": False, "gaze_enabled": False})
    assert score_disabled == 0.0


def test_proctoring_rest_endpoints(client, examiner_headers, student_headers, db_session, test_student, test_examiner):
    from datetime import datetime, timezone, timedelta
    from app.models import Exam, ExamSession

    now = datetime.now(timezone.utc)
    exam = Exam(
        created_by=test_examiner.id,
        title="Proctor Exam",
        subject="Physics",
        duration_minutes=30,
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(hours=1)
    )
    db_session.add(exam)
    db_session.flush()

    session = ExamSession(
        exam_id=exam.id,
        student_id=test_student.id,
        suspicion_score=80.0,
        is_flagged=True
    )
    db_session.add(session)
    db_session.commit()

    # Examiner lists sessions
    res = client.get(f"/api/v1/exams/{exam.id}/proctoring/sessions?flagged_only=true", headers=examiner_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["suspicion_score"] == 80.0
    assert data[0]["is_flagged"] is True

    # Student cannot access examiner proctoring endpoint
    res_student = client.get(f"/api/v1/exams/{exam.id}/proctoring/sessions", headers=student_headers)
    assert res_student.status_code == 403
