from datetime import datetime, timedelta, timezone
import pytest


def test_invalid_time_window(client, examiner_headers):
    now = datetime.now(timezone.utc)
    res = client.post("/api/v1/exams", headers=examiner_headers, json={
        "title": "Math Final",
        "subject": "Mathematics",
        "duration_minutes": 60,
        "start_time": (now + timedelta(hours=2)).isoformat(),
        "end_time": (now + timedelta(hours=1)).isoformat()
    })
    assert res.status_code == 422


def test_duration_exceeds_window(client, examiner_headers):
    now = datetime.now(timezone.utc)
    res = client.post("/api/v1/exams", headers=examiner_headers, json={
        "title": "Math Final",
        "subject": "Mathematics",
        "duration_minutes": 120,
        "start_time": (now + timedelta(hours=1)).isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat()
    })
    assert res.status_code == 422


def test_insufficient_questions_selection_rules(client, examiner_headers):
    now = datetime.now(timezone.utc)
    res = client.post("/api/v1/exams", headers=examiner_headers, json={
        "title": "Math Final",
        "subject": "Mathematics",
        "duration_minutes": 60,
        "start_time": (now + timedelta(hours=1)).isoformat(),
        "end_time": (now + timedelta(hours=3)).isoformat(),
        "selection_rules": {
            "difficulty": {"easy": 10}
        }
    })
    assert res.status_code == 409


def test_exam_crud_publish_edit_lock(client, examiner_headers, admin_headers):
    now = datetime.now(timezone.utc)
    # Create
    res = client.post("/api/v1/exams", headers=examiner_headers, json={
        "title": "Physics Exam",
        "subject": "Physics",
        "duration_minutes": 45,
        "start_time": (now - timedelta(minutes=10)).isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat()
    })
    assert res.status_code == 201
    exam_id = res.json()["id"]

    # Publish
    res_pub = client.post(f"/api/v1/exams/{exam_id}/publish", headers=examiner_headers)
    assert res_pub.status_code == 200
    assert res_pub.json()["status"] == "published"

    # Edit after publish and start => 400 Bad Request
    res_edit = client.put(f"/api/v1/exams/{exam_id}", headers=examiner_headers, json={
        "title": "Physics Exam Updated"
    })
    assert res_edit.status_code == 400

    # List exams
    res_list = client.get("/api/v1/exams?subject=Physics", headers=examiner_headers)
    assert res_list.status_code == 200

    # Delete
    res_del = client.delete(f"/api/v1/exams/{exam_id}", headers=admin_headers)
    assert res_del.status_code == 204
