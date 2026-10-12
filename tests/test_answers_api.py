import io
import pytest
from app.models import QuestionBank, QuestionType, Difficulty, Exam, ExamQuestion, ExamSession, Option, SessionStatus


def test_upsert_answer_and_validations(client, student_headers, examiner_headers, db_session, test_student, test_examiner):
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)

    # Question 1: Short answer
    q1 = QuestionBank(
        created_by=test_examiner.id,
        question_type=QuestionType.SHORT_ANSWER,
        subject="History",
        difficulty=Difficulty.EASY,
        question_text="Who was Napoleon?",
        marks=5.0
    )
    db_session.add(q1)
    db_session.flush()

    exam = Exam(
        created_by=test_examiner.id,
        title="History Exam",
        subject="History",
        duration_minutes=30,
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(hours=1)
    )
    db_session.add(exam)
    db_session.flush()

    eq = ExamQuestion(exam_id=exam.id, question_id=q1.id)
    db_session.add(eq)

    session = ExamSession(
        exam_id=exam.id,
        student_id=test_student.id,
        status=SessionStatus.IN_PROGRESS,
        server_deadline=now + timedelta(minutes=20),
        generated_paper=[{"question_id": q1.id, "question_type": "short_answer"}]
    )
    db_session.add(session)
    db_session.commit()

    # 1. Upsert answer
    res = client.put(f"/api/v1/sessions/{session.id}/answers/{q1.id}", headers=student_headers, json={
        "question_id": q1.id,
        "text_answer": "Napoleon was a French military commander and emperor."
    })
    assert res.status_code == 200
    assert res.json()["word_count"] == 8

    # 2. Get saved answers
    res_get = client.get(f"/api/v1/sessions/{session.id}/answers", headers=student_headers)
    assert res_get.status_code == 200
    assert len(res_get.json()) == 1


def test_image_upload_magic_bytes_and_thumbnail(client, student_headers, examiner_headers, db_session, test_student, test_examiner):
    from datetime import datetime, timezone, timedelta
    from PIL import Image

    now = datetime.now(timezone.utc)

    q = QuestionBank(
        created_by=test_examiner.id,
        question_type=QuestionType.IMAGE_UPLOAD,
        subject="Art",
        difficulty=Difficulty.EASY,
        question_text="Upload diagram",
        marks=10.0
    )
    db_session.add(q)
    db_session.flush()

    exam = Exam(
        created_by=test_examiner.id,
        title="Art Exam",
        subject="Art",
        duration_minutes=30,
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(hours=1)
    )
    db_session.add(exam)
    db_session.flush()

    session = ExamSession(
        exam_id=exam.id,
        student_id=test_student.id,
        status=SessionStatus.IN_PROGRESS,
        server_deadline=now + timedelta(minutes=20),
        generated_paper=[{"question_id": q.id, "question_type": "image_upload"}]
    )
    db_session.add(session)
    db_session.commit()

    # Create real valid PNG image bytes
    img = Image.new("RGB", (100, 100), color="red")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    valid_png_bytes = img_byte_arr.getvalue()

    # 1. Reject fake image (wrong magic bytes)
    res_fake = client.post(
        f"/api/v1/sessions/{session.id}/answers/{q.id}/image",
        headers=student_headers,
        files={"file": ("test.png", b"not-a-real-image-payload", "image/png")}
    )
    assert res_fake.status_code == 400

    # 2. Upload valid image
    res_valid = client.post(
        f"/api/v1/sessions/{session.id}/answers/{q.id}/image",
        headers=student_headers,
        files={"file": ("diagram.png", valid_png_bytes, "image/png")}
    )
    assert res_valid.status_code == 200
    data = res_valid.json()
    assert data["image_answer_url"].startswith("/static/uploads/")
    assert data["thumbnail_url"].startswith("/static/uploads/")
