import io
from datetime import datetime, timezone, timedelta
from PIL import Image
import pytest

from app.models import (
    Exam, ExamStatus, QuestionBank, QuestionType, Difficulty,
    Option, ExamQuestion, ExamSession
)


def create_test_exam_with_questions(db, examiner):
    now = datetime.now(timezone.utc)
    exam = Exam(
        created_by=examiner.id,
        title="Answers Test Exam",
        subject="Computer Science",
        duration_minutes=60,
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(minutes=60),
        status=ExamStatus.PUBLISHED
    )
    db.add(exam)
    db.commit()

    # MCQ Question
    q_mcq = QuestionBank(
        created_by=examiner.id,
        question_type=QuestionType.MCQ,
        subject="CS",
        difficulty=Difficulty.EASY,
        question_text="What is 2+2?",
        marks=5.0
    )
    db.add(q_mcq)
    db.commit()
    opt1 = Option(question_id=q_mcq.id, option_text="3", is_correct=False)
    opt2 = Option(question_id=q_mcq.id, option_text="4", is_correct=True)
    db.add_all([opt1, opt2])
    db.commit()

    # Short Answer Question
    q_short = QuestionBank(
        created_by=examiner.id,
        question_type=QuestionType.SHORT_ANSWER,
        subject="CS",
        difficulty=Difficulty.EASY,
        question_text="Explain recursion briefly.",
        marks=10.0
    )
    db.add(q_short)
    db.commit()

    # Image Upload Question
    q_img = QuestionBank(
        created_by=examiner.id,
        question_type=QuestionType.IMAGE_UPLOAD,
        subject="CS",
        difficulty=Difficulty.MEDIUM,
        question_text="Upload diagram.",
        marks=15.0
    )
    db.add(q_img)
    db.commit()

    # Exam questions
    eq1 = ExamQuestion(exam_id=exam.id, question_id=q_mcq.id, order_index=1)
    eq2 = ExamQuestion(exam_id=exam.id, question_id=q_short.id, order_index=2)
    eq3 = ExamQuestion(exam_id=exam.id, question_id=q_img.id, order_index=3)
    db.add_all([eq1, eq2, eq3])
    db.commit()

    return exam, q_mcq, opt1, opt2, q_short, q_img


def test_mcq_answer_validation(client, db_session, test_examiner, test_student, student_headers):
    exam, q_mcq, opt1, opt2, _, _ = create_test_exam_with_questions(db_session, test_examiner)

    # Start session
    acc_res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    access_token = acc_res.json()["exam_access_token"]
    start_res = client.post(f"/api/v1/exams/{exam.id}/start", json={"exam_access_token": access_token}, headers=student_headers)
    session_id = start_res.json()["session_id"]

    # Reject MCQ with 2 options
    res_bad = client.put(
        f"/api/v1/sessions/{session_id}/answers/{q_mcq.id}",
        json={"selected_option_ids": [opt1.id, opt2.id]},
        headers=student_headers
    )
    assert res_bad.status_code == 400

    # Reject invalid option ID
    res_fake = client.put(
        f"/api/v1/sessions/{session_id}/answers/{q_mcq.id}",
        json={"selected_option_ids": ["non_existent_opt_id"]},
        headers=student_headers
    )
    assert res_fake.status_code == 400

    # Success MCQ with 1 option
    res_ok = client.put(
        f"/api/v1/sessions/{session_id}/answers/{q_mcq.id}",
        json={"selected_option_ids": [opt2.id]},
        headers=student_headers
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["selected_option_ids"] == [opt2.id]


def test_short_answer_word_count_limits(client, db_session, test_examiner, test_student, student_headers):
    exam, _, _, _, q_short, _ = create_test_exam_with_questions(db_session, test_examiner)

    acc_res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    access_token = acc_res.json()["exam_access_token"]
    start_res = client.post(f"/api/v1/exams/{exam.id}/start", json={"exam_access_token": access_token}, headers=student_headers)
    session_id = start_res.json()["session_id"]

    # Empty text -> word count 0 -> 400 bad request
    res_empty = client.put(
        f"/api/v1/sessions/{session_id}/answers/{q_short.id}",
        json={"text_answer": ""},
        headers=student_headers
    )
    assert res_empty.status_code == 400

    # Text > 150 words -> 400 bad request
    long_text = "word " * 151
    res_too_long = client.put(
        f"/api/v1/sessions/{session_id}/answers/{q_short.id}",
        json={"text_answer": long_text},
        headers=student_headers
    )
    assert res_too_long.status_code == 400

    # Valid text
    valid_text = "Recursion is a function calling itself until a base condition is met."
    res_ok = client.put(
        f"/api/v1/sessions/{session_id}/answers/{q_short.id}",
        json={"text_answer": valid_text},
        headers=student_headers
    )
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert data["word_count"] == 12
    assert "Recursion" in data["text_answer"]


def test_image_upload_answer(client, db_session, test_examiner, test_student, student_headers):
    exam, _, _, _, _, q_img = create_test_exam_with_questions(db_session, test_examiner)

    acc_res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    access_token = acc_res.json()["exam_access_token"]
    start_res = client.post(f"/api/v1/exams/{exam.id}/start", json={"exam_access_token": access_token}, headers=student_headers)
    session_id = start_res.json()["session_id"]

    # Create dummy PNG in memory using Pillow
    img = Image.new('RGB', (100, 100), color='blue')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    img_bytes = buf.getvalue()

    files = {"file": ("diagram.png", img_bytes, "image/png")}
    upload_res = client.post(
        f"/api/v1/sessions/{session_id}/answers/{q_img.id}/image",
        files=files,
        headers=student_headers
    )
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert "image_answer_url" in data and data["image_answer_url"].startswith("/uploads/")
    assert "thumbnail_url" in data and data["thumbnail_url"].startswith("/uploads/")


def test_get_saved_answers(client, db_session, test_examiner, test_student, student_headers):
    exam, q_mcq, opt1, opt2, _, _ = create_test_exam_with_questions(db_session, test_examiner)

    acc_res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    access_token = acc_res.json()["exam_access_token"]
    start_res = client.post(f"/api/v1/exams/{exam.id}/start", json={"exam_access_token": access_token}, headers=student_headers)
    session_id = start_res.json()["session_id"]

    client.put(
        f"/api/v1/sessions/{session_id}/answers/{q_mcq.id}",
        json={"selected_option_ids": [opt2.id]},
        headers=student_headers
    )

    get_res = client.get(f"/api/v1/sessions/{session_id}/answers", headers=student_headers)
    assert get_res.status_code == 200
    answers = get_res.json()
    assert len(answers) == 1
    assert answers[0]["question_id"] == q_mcq.id
    assert answers[0]["selected_option_ids"] == [opt2.id]
    # Ensure correct answers / marks are NOT exposed
    assert "is_correct" not in answers[0]
    assert "marks_awarded" not in answers[0]
