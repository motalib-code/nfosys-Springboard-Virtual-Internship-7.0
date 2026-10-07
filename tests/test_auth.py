import pytest


def test_login(client, test_student):
    res = client.post("/api/v1/auth/login", json={
        "email": test_student.email,
        "password": "password123"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data

    res_bad = client.post("/api/v1/auth/login", json={
        "email": test_student.email,
        "password": "wrongpassword"
    })
    assert res_bad.status_code == 401


def test_me_endpoint(client, student_headers, test_student):
    res = client.get("/api/v1/auth/me", headers=student_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == test_student.email
    assert data["role"] == "student"


def test_refresh_token(client, test_student):
    login_res = client.post("/api/v1/auth/login", json={
        "email": test_student.email,
        "password": "password123"
    }).json()
    refresh_token = login_res["refresh_token"]

    ref_res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert ref_res.status_code == 200
    assert "access_token" in ref_res.json()


def test_admin_register_examiner(client, admin_headers):
    res = client.post("/api/v1/auth/register", headers=admin_headers, json={
        "email": "created_examiner@example.com",
        "password": "password123",
        "name": "Created Examiner",
        "role": "examiner"
    })
    assert res.status_code == 201
    assert res.json()["role"] == "examiner"


def test_role_permissions(client, student_headers, examiner_headers):
    res = client.post("/api/v1/questions", headers=student_headers, json={
        "question_type": "MCQ",
        "subject": "Physics",
        "difficulty": "easy",
        "question_text": "What is speed?",
        "marks": 2.0,
        "options": [
            {"option_text": "Option A", "is_correct": True},
            {"option_text": "Option B", "is_correct": False}
        ]
    })
    assert res.status_code == 403

    res_ok = client.post("/api/v1/questions", headers=examiner_headers, json={
        "question_type": "MCQ",
        "subject": "Physics",
        "difficulty": "easy",
        "question_text": "What is speed?",
        "marks": 2.0,
        "options": [
            {"option_text": "Option A", "is_correct": True},
            {"option_text": "Option B", "is_correct": False}
        ]
    })
    assert res_ok.status_code == 201


def test_register_role_restriction(client, student_headers):
    res = client.post("/api/v1/auth/register", headers=student_headers, json={
        "email": "new_examiner@example.com",
        "password": "password123",
        "name": "New Examiner",
        "role": "examiner"
    })
    assert res.status_code == 403
