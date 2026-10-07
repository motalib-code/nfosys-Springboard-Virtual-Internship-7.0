from datetime import datetime, timedelta, timezone
import pytest


def test_paper_generator_determinism(client, examiner_headers, student_headers, test_student, test_student_2):
    for i in range(5):
        client.post("/api/v1/questions", headers=examiner_headers, json={
            "question_type": "MCQ",
            "subject": "Biology",
            "difficulty": "easy",
            "question_text": f"Biology Question {i}",
            "marks": 2.0,
            "options": [
                {"option_text": f"Option A{i}", "is_correct": True},
                {"option_text": f"Option B{i}", "is_correct": False}
            ]
        })

    now = datetime.now(timezone.utc)
    res_exam = client.post("/api/v1/exams", headers=examiner_headers, json={
        "title": "Biology Quiz",
        "subject": "Biology",
        "duration_minutes": 30,
        "start_time": (now - timedelta(minutes=5)).isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "selection_rules": {
            "difficulty": {"easy": 3}
        }
    })
    assert res_exam.status_code == 201
    exam_id = res_exam.json()["id"]

    client.post(f"/api/v1/exams/{exam_id}/publish", headers=examiner_headers)

    res_token1 = client.post(f"/api/v1/exams/{exam_id}/access-token", headers=student_headers)
    access_token1 = res_token1.json()["exam_access_token"]

    res_start1 = client.post(f"/api/v1/exams/{exam_id}/start", headers=student_headers, json={
        "exam_access_token": access_token1
    })
    session_id1 = res_start1.json()["session_id"]
    session_token1 = res_start1.json()["session_token"]

    headers_s1 = {"Authorization": f"Bearer {session_token1}"}
    paper1_a = client.get(f"/api/v1/sessions/{session_id1}/paper", headers=headers_s1).json()
    paper1_b = client.get(f"/api/v1/sessions/{session_id1}/paper", headers=headers_s1).json()

    assert paper1_a["paper"]["seed"] == paper1_b["paper"]["seed"]
    assert [q["question_id"] for q in paper1_a["paper"]["questions"]] == [q["question_id"] for q in paper1_b["paper"]["questions"]]

    token_s2 = create_student_token(test_student_2)
    headers_s2_auth = {"Authorization": f"Bearer {token_s2}"}

    res_token2 = client.post(f"/api/v1/exams/{exam_id}/access-token", headers=headers_s2_auth)
    access_token2 = res_token2.json()["exam_access_token"]

    res_start2 = client.post(f"/api/v1/exams/{exam_id}/start", headers=headers_s2_auth, json={
        "exam_access_token": access_token2
    })
    session_id2 = res_start2.json()["session_id"]
    session_token2 = res_start2.json()["session_token"]

    headers_s2 = {"Authorization": f"Bearer {session_token2}"}
    paper2 = client.get(f"/api/v1/sessions/{session_id2}/paper", headers=headers_s2).json()

    assert paper1_a["paper"]["seed"] != paper2["paper"]["seed"]


def create_student_token(student_user):
    from app.core.security import create_access_token
    return create_access_token(student_user.id, student_user.role.value)


def test_heartbeat_token_rotation(client, student_headers, examiner_headers):
    now = datetime.now(timezone.utc)
    res_exam = client.post("/api/v1/exams", headers=examiner_headers, json={
        "title": "General Quiz",
        "subject": "General",
        "duration_minutes": 30,
        "start_time": (now - timedelta(minutes=5)).isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat()
    })
    exam_id = res_exam.json()["id"]
    client.post(f"/api/v1/exams/{exam_id}/publish", headers=examiner_headers)

    res_token = client.post(f"/api/v1/exams/{exam_id}/access-token", headers=student_headers)
    access_token = res_token.json()["exam_access_token"]

    res_start = client.post(f"/api/v1/exams/{exam_id}/start", headers=student_headers, json={
        "exam_access_token": access_token
    })
    session_id = res_start.json()["session_id"]
    initial_session_token = res_start.json()["session_token"]

    headers_initial = {"Authorization": f"Bearer {initial_session_token}"}
    res_hb1 = client.post(f"/api/v1/sessions/{session_id}/heartbeat", headers=headers_initial)
    assert res_hb1.status_code == 200
    fresh_session_token = res_hb1.json()["session_token"]

    res_hb_old = client.post(f"/api/v1/sessions/{session_id}/heartbeat", headers=headers_initial)
    assert res_hb_old.status_code == 401

    headers_fresh = {"Authorization": f"Bearer {fresh_session_token}"}
    res_hb_fresh = client.post(f"/api/v1/sessions/{session_id}/heartbeat", headers=headers_fresh)
    assert res_hb_fresh.status_code == 200


def test_answer_submission_proctor_event_submit(client, student_headers, examiner_headers):
    now = datetime.now(timezone.utc)
    # Create question & exam
    q_res = client.post("/api/v1/questions", headers=examiner_headers, json={
        "question_type": "short_answer",
        "subject": "CS",
        "difficulty": "easy",
        "question_text": "What is Python?",
        "marks": 5.0,
        "model_answer": "Python is a programming language"
    })
    q_id = q_res.json()["id"]

    res_exam = client.post("/api/v1/exams", headers=examiner_headers, json={
        "title": "CS 101",
        "subject": "CS",
        "duration_minutes": 30,
        "start_time": (now - timedelta(minutes=5)).isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "question_ids": [q_id]
    })
    exam_id = res_exam.json()["id"]
    client.post(f"/api/v1/exams/{exam_id}/publish", headers=examiner_headers)

    res_token = client.post(f"/api/v1/exams/{exam_id}/access-token", headers=student_headers)
    access_token = res_token.json()["exam_access_token"]

    res_start = client.post(f"/api/v1/exams/{exam_id}/start", headers=student_headers, json={
        "exam_access_token": access_token
    })
    session_id = res_start.json()["session_id"]
    session_token = res_start.json()["session_token"]
    headers_session = {"Authorization": f"Bearer {session_token}"}

    # Submit answer
    ans_res = client.post(f"/api/v1/sessions/{session_id}/answers", headers=headers_session, json={
        "question_id": q_id,
        "text_answer": "Python is an interpreted language"
    })
    assert ans_res.status_code == 200

    # Record proctor event
    evt_res = client.post(f"/api/v1/sessions/{session_id}/events", headers=headers_session, json={
        "event_type": "tab_switch",
        "payload": {"details": "Switched tab"},
        "severity": "warning"
    })
    assert evt_res.status_code == 201

    # Submit session
    sub_res = client.post(f"/api/v1/sessions/{session_id}/submit", headers=headers_session)
    assert sub_res.status_code == 200
    assert sub_res.json()["status"] == "submitted"
