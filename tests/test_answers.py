import io
from PIL import Image
import pytest
from app.models import QuestionBank, QuestionType, Option, ExamQuestion

def test_answers_workflow(client, db_session, test_examiner, test_student, student_headers):
    # Setup Question MCQ
    q_mcq = QuestionBank(
        created_by=test_examiner.id,
        question_type=QuestionType.MCQ,
        subject="CS",
        difficulty="easy",
        question_text="2+2?",
        marks=2.0
    )
    db_session.add(q_mcq)
    db_session.flush()

    opt1 = Option(question_id=q_mcq.id, option_text="3", is_correct=False)
    opt2 = Option(question_id=q_mcq.id, option_text="4", is_correct=True)
    db_session.add_all([opt1, opt2])

    # Setup Question Short Answer
    q_short = QuestionBank(
        created_by=test_examiner.id,
        question_type=QuestionType.SHORT_ANSWER,
        subject="CS",
        difficulty="easy",
        question_text="Explain RAM",
        marks=5.0
    )
    db_session.add(q_short)
    db_session.commit()

    # Create exam with these questions in subject Computer Science
    from tests.test_timed_session_engine import create_published_exam
    exam = create_published_exam(db_session, test_examiner)
    q_mcq.subject = exam.subject
    q_short.subject = exam.subject
    db_session.commit()

    eq1 = ExamQuestion(exam_id=exam.id, question_id=q_mcq.id, order_index=0)
    eq2 = ExamQuestion(exam_id=exam.id, question_id=q_short.id, order_index=1)
    db_session.add_all([eq1, eq2])
    db_session.commit()

    # Get exam access token and start session
    res = client.post(f"/api/v1/exams/{exam.id}/access-token", headers=student_headers)
    token = res.json()["exam_access_token"]
    start_res = client.post(f"/api/v1/exams/{exam.id}/start", json={"exam_access_token": token}, headers=student_headers)
    session_id = start_res.json()["session_id"]

    # 1. Submit MCQ answer via PUT /sessions/{id}/answers/{question_id}
    ans_res = client.put(
        f"/api/v1/sessions/{session_id}/answers/{q_mcq.id}",
        json={"question_id": q_mcq.id, "selected_option_ids": [opt2.id]},
        headers=student_headers
    )
    assert ans_res.status_code == 200
    assert ans_res.json()["selected_option_ids"] == [opt2.id]

    # 2. Reject option from another question or non-existent
    bad_ans = client.put(
        f"/api/v1/sessions/{session_id}/answers/{q_mcq.id}",
        json={"question_id": q_mcq.id, "selected_option_ids": ["invalid-id"]},
        headers=student_headers
    )
    assert bad_ans.status_code == 400

    # 3. Submit Short Answer with word count validation
    short_ans = client.put(
        f"/api/v1/sessions/{session_id}/answers/{q_short.id}",
        json={"question_id": q_short.id, "text_answer": "Random Access Memory"},
        headers=student_headers
    )
    assert short_ans.status_code == 200
    assert short_ans.json()["word_count"] == 3

    # 4. GET /sessions/{id}/answers
    get_ans = client.get(f"/api/v1/sessions/{session_id}/answers", headers=student_headers)
    assert get_ans.status_code == 200
    assert len(get_ans.json()) == 2

    # 5. Upload image answer (valid JPEG and thumbnail check)
    img = Image.new("RGB", (100, 100), color="red")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_bytes = img_byte_arr.getvalue()

    files = {"file": ("test.jpg", img_bytes, "image/jpeg")}
    img_res = client.post(
        f"/api/v1/sessions/{session_id}/answers/{q_short.id}/image",
        files=files,
        headers=student_headers
    )
    assert img_res.status_code == 200
    data = img_res.json()
    assert "/uploads/images/" in data["image_answer_url"]
    assert "/uploads/thumbnails/" in data["thumbnail_url"]

    # 6. Upload invalid image format (fake magic bytes)
    bad_files = {"file": ("test.txt", b"Hello world text file", "text/plain")}
    bad_img_res = client.post(
        f"/api/v1/sessions/{session_id}/answers/{q_short.id}/image",
        files=bad_files,
        headers=student_headers
    )
    assert bad_img_res.status_code == 400
