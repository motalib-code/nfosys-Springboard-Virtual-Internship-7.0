import pytest
from unittest.mock import patch
from app.models import ProctorEventType
from app.services.suspicion_scorer import SuspicionScorer
from tests.test_timed_session_engine import create_published_exam

def test_suspicion_scorer_purity_and_caps():
    events = [
        {"event_type": ProctorEventType.GAZE_AWAY},
        {"event_type": ProctorEventType.GAZE_AWAY},
        {"event_type": ProctorEventType.GAZE_AWAY},
        {"event_type": ProctorEventType.GAZE_AWAY},
        {"event_type": ProctorEventType.GAZE_AWAY},  # 5 * 8.0 = 40.0, cap is 32.0
        {"event_type": ProctorEventType.NO_FACE}      # + 15.0 = 47.0
    ]

    score = SuspicionScorer.compute_score(events)
    assert score == 47.0

def test_suspicion_scorer_disabled_settings():
    events = [
        {"event_type": ProctorEventType.GAZE_AWAY},
        {"event_type": ProctorEventType.NO_FACE}
    ]
    # Disable webcam and gaze
    settings = {"webcam_enabled": False, "gaze_enabled": False}
    score = SuspicionScorer.compute_score(events, settings=settings)
    assert score == 0.0

def test_proctoring_websocket_flow(client, db_session, test_examiner, test_student, student_headers):
    exam = create_published_exam(db_session, test_examiner)

    res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    access_token = res.json()["exam_access_token"]
    start_res = client.post(f"/api/v1/exams/{exam.id}/start", json={"exam_access_token": access_token}, headers=student_headers)
    session_id = start_res.json()["session_id"]
    session_token = start_res.json()["session_token"]

    # Connect to WebSocket with SessionLocal mocked to db_session
    with patch("app.api.v1.proctoring.SessionLocal", return_value=db_session):
        with client.websocket_connect(f"/api/v1/ws/proctor/{session_id}?token={session_token}") as websocket:
            payload = {
                "seq": 1,
                "face_count": 0,
                "gaze": {"on_screen": False},
                "tab_visible": True,
                "window_focused": True
            }
            websocket.send_json(payload)
            response = websocket.receive_json()

            assert response["ack"] == 1
            assert response["suspicion_score"] > 0
            assert "server_time" in response
