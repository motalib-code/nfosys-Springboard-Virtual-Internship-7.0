from datetime import datetime, timedelta, timezone
import pytest


def test_question_crud_and_filters(client, examiner_headers, admin_headers):
    # Create question
    res = client.post("/api/v1/questions", headers=examiner_headers, json={
        "question_type": "multi_select",
        "subject": "Chemistry",
        "difficulty": "hard",
        "question_text": "Select noble gases",
        "marks": 4.0,
        "options": [
            {"option_text": "Helium", "is_correct": True},
            {"option_text": "Neon", "is_correct": True},
            {"option_text": "Oxygen", "is_correct": False}
        ],
        "tags": ["chemistry", "periodic-table"]
    })
    assert res.status_code == 201
    q_data = res.json()
    q_id = q_data["id"]

    # Filter questions
    res_list = client.get("/api/v1/questions?subject=Chemistry&difficulty=hard", headers=examiner_headers)
    assert res_list.status_code == 200
    assert len(res_list.json()["items"]) >= 1

    # Get single question
    res_get = client.get(f"/api/v1/questions/{q_id}", headers=examiner_headers)
    assert res_get.status_code == 200

    # Admin update question
    res_up = client.put(f"/api/v1/questions/{q_id}", headers=admin_headers, json={
        "marks": 5.0
    })
    assert res_up.status_code == 200
    assert res_up.json()["marks"] == 5.0

    # Delete question
    res_del = client.delete(f"/api/v1/questions/{q_id}", headers=examiner_headers)
    assert res_del.status_code == 204


def test_image_upload_and_long_answer(client, examiner_headers):
    # Image upload valid
    res_img = client.post("/api/v1/questions", headers=examiner_headers, json={
        "question_type": "image_upload",
        "subject": "Art",
        "difficulty": "medium",
        "question_text": "Upload drawing",
        "marks": 10.0,
        "max_marks_for_image": 10.0
    })
    assert res_img.status_code == 201

    # Long answer valid
    res_long = client.post("/api/v1/questions", headers=examiner_headers, json={
        "question_type": "long_answer",
        "subject": "History",
        "difficulty": "hard",
        "question_text": "Discuss WW2",
        "marks": 15.0,
        "model_answer": "Detailed history essay..."
    })
    assert res_long.status_code == 201
