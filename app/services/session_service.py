from typing import List, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
import io
import re
from PIL import Image
from app.models import ExamSession, Exam, Answer, ProctorEvent, SessionStatus, User, UserRole, ProctorEventType, SubmittedReason, QuestionBank, QuestionType
from app.schemas.session import AnswerSubmitRequest, AnswerUpsertRequest, ProctorEventCreate
from app.services.paper_generator import PaperGenerator
from app.services.storage import get_storage_backend
from app.services.evaluation import EvaluationService
from app.core.config import settings
from app.core.exceptions import NotFoundException, PermissionDeniedException, BadRequestException, ConflictException


class SessionService:
    @staticmethod
    def _validate_session_active_and_within_deadline(db: Session, session: ExamSession) -> None:
        if session.status not in [SessionStatus.IN_PROGRESS, SessionStatus.FLAGGED]:
            raise BadRequestException(f"Cannot perform operation when session status is {session.status.value}")

        now = datetime.now(timezone.utc)
        if session.server_deadline:
            deadline = session.server_deadline if session.server_deadline.tzinfo is not None else session.server_deadline.replace(tzinfo=timezone.utc)
            grace_delta = timedelta(seconds=settings.SERVER_DEADLINE_GRACE_SECONDS)
            if now > deadline + grace_delta:
                session.status = SessionStatus.AUTO_SUBMITTED
                session.submitted_reason = SubmittedReason.TIME_EXPIRED
                session.submitted_at = now
                db.commit()
                raise ConflictException("Exam session deadline has passed. Session auto-submitted.")

    @staticmethod
    def get_time_remaining(db: Session, session_id: str, current_user: User) -> dict:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied")

        now = datetime.now(timezone.utc)
        seconds_remaining = 0
        if session.server_deadline and session.status in [SessionStatus.IN_PROGRESS, SessionStatus.FLAGGED]:
            deadline = session.server_deadline if session.server_deadline.tzinfo is not None else session.server_deadline.replace(tzinfo=timezone.utc)
            diff = (deadline - now).total_seconds()
            seconds_remaining = max(0, int(diff))

        return {
            "session_id": session.id,
            "seconds_remaining": seconds_remaining,
            "server_time": now,
            "server_deadline": session.server_deadline,
            "status": session.status
        }

    @staticmethod
    def get_session_paper(db: Session, session_id: str, current_user: User) -> dict:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied to another student's session")

        # Generate paper if not generated yet
        if not session.generated_paper:
            exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
            paper_data = PaperGenerator.generate_paper(db, exam, session.student_id)
            session.paper_seed = paper_data["seed"]
            session.generated_paper = paper_data["questions"]
            db.commit()
            db.refresh(session)

        return {
            "session_id": session.id,
            "status": session.status,
            "paper": {
                "seed": session.paper_seed,
                "questions": session.generated_paper
            }
        }

    @staticmethod
    def upsert_answer(db: Session, session_id: str, question_id: str, answer_in: AnswerUpsertRequest, current_user: User) -> dict:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied")

        SessionService._validate_session_active_and_within_deadline(db, session)

        if not session.generated_paper:
            exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
            paper_data = PaperGenerator.generate_paper(db, exam, session.student_id)
            session.paper_seed = paper_data["seed"]
            session.generated_paper = paper_data["questions"]

        paper_q_ids = [q.get("question_id") or q.get("id") for q in session.generated_paper]
        if question_id not in paper_q_ids:
            raise BadRequestException("Question is not part of this candidate's exam paper")

        question = db.query(QuestionBank).filter(QuestionBank.id == question_id).first()
        if not question:
            raise NotFoundException("Question not found")

        word_count = None
        cleaned_text = None

        if question.question_type == QuestionType.MCQ:
            if not answer_in.selected_option_ids or len(answer_in.selected_option_ids) != 1:
                raise BadRequestException("MCQ requires exactly 1 selected option")
            valid_opt_ids = {opt.id for opt in question.options}
            if not set(answer_in.selected_option_ids).issubset(valid_opt_ids):
                raise BadRequestException("Invalid option selection for question")

        elif question.question_type == QuestionType.MULTI_SELECT:
            if not answer_in.selected_option_ids or len(answer_in.selected_option_ids) < 1:
                raise BadRequestException("Multi-select requires at least 1 selected option")
            valid_opt_ids = {opt.id for opt in question.options}
            if not set(answer_in.selected_option_ids).issubset(valid_opt_ids):
                raise BadRequestException("Invalid option selection for question")

        elif question.question_type in [QuestionType.SHORT_ANSWER, QuestionType.LONG_ANSWER]:
            raw_text = answer_in.text_answer or ""
            cleaned_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw_text).strip()
            words = cleaned_text.split()
            word_count = len(words)

            min_w = 1
            max_w = 150 if question.question_type == QuestionType.SHORT_ANSWER else 1000
            if word_count < min_w or word_count > max_w:
                raise BadRequestException(f"{question.question_type.value} word count ({word_count}) must be between {min_w} and {max_w} words")

        now = datetime.now(timezone.utc)
        session.last_activity_at = now

        existing = db.query(Answer).filter(
            Answer.session_id == session_id,
            Answer.question_id == question_id
        ).first()

        if existing:
            existing.selected_option_ids = answer_in.selected_option_ids
            existing.text_answer = cleaned_text if question.question_type in [QuestionType.SHORT_ANSWER, QuestionType.LONG_ANSWER] else answer_in.text_answer
            existing.answered_at = now
            ans = existing
        else:
            ans = Answer(
                session_id=session_id,
                question_id=question_id,
                selected_option_ids=answer_in.selected_option_ids,
                text_answer=cleaned_text if question.question_type in [QuestionType.SHORT_ANSWER, QuestionType.LONG_ANSWER] else answer_in.text_answer,
                answered_at=now
            )
            db.add(ans)

        db.commit()
        db.refresh(ans)

        return {
            "id": ans.id,
            "session_id": ans.session_id,
            "question_id": ans.question_id,
            "selected_option_ids": ans.selected_option_ids,
            "text_answer": ans.text_answer,
            "word_count": word_count,
            "image_answer_url": ans.image_answer_url,
            "thumbnail_url": ans.thumbnail_url,
            "answered_at": ans.answered_at
        }

    @staticmethod
    def upload_image_answer(db: Session, session_id: str, question_id: str, file_bytes: bytes, filename: str, current_user: User) -> dict:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied")

        SessionService._validate_session_active_and_within_deadline(db, session)

        if len(file_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
            raise BadRequestException(f"File size exceeds maximum allowed limit ({settings.MAX_UPLOAD_SIZE_BYTES // (1024*1024)}MB)")

        question = db.query(QuestionBank).filter(QuestionBank.id == question_id).first()
        if not question or question.question_type != QuestionType.IMAGE_UPLOAD:
            raise BadRequestException("Question does not accept image uploads")

        try:
            img = Image.open(io.BytesIO(file_bytes))
            if img.format not in ['JPEG', 'PNG', 'WEBP']:
                raise BadRequestException("Invalid image MIME/format. Only JPG, PNG, and WEBP allowed.")
        except Exception:
            raise BadRequestException("Invalid or corrupted image file")

        out_buf = io.BytesIO()
        img.save(out_buf, format="PNG")
        clean_bytes = out_buf.getvalue()

        thumb_img = img.copy()
        thumb_img.thumbnail((320, 320))
        thumb_buf = io.BytesIO()
        thumb_img.save(thumb_buf, format="PNG")
        thumb_bytes = thumb_buf.getvalue()

        storage = get_storage_backend()
        image_url = storage.save_file(clean_bytes, filename, subfolder="answers")
        thumb_url = storage.save_file(thumb_bytes, f"thumb_{filename}", subfolder="answers/thumbnails")

        now = datetime.now(timezone.utc)
        session.last_activity_at = now

        existing = db.query(Answer).filter(
            Answer.session_id == session_id,
            Answer.question_id == question_id
        ).first()

        if existing:
            existing.image_answer_url = image_url
            existing.thumbnail_url = thumb_url
            existing.answered_at = now
            ans = existing
        else:
            ans = Answer(
                session_id=session_id,
                question_id=question_id,
                image_answer_url=image_url,
                thumbnail_url=thumb_url,
                answered_at=now
            )
            db.add(ans)

        db.commit()
        db.refresh(ans)

        return {
            "id": ans.id,
            "session_id": ans.session_id,
            "question_id": ans.question_id,
            "selected_option_ids": ans.selected_option_ids,
            "text_answer": ans.text_answer,
            "word_count": None,
            "image_answer_url": ans.image_answer_url,
            "thumbnail_url": ans.thumbnail_url,
            "answered_at": ans.answered_at
        }

    @staticmethod
    def get_student_answers(db: Session, session_id: str, current_user: User) -> List[dict]:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied to another student's session")

        answers = db.query(Answer).filter(Answer.session_id == session_id).all()
        result = []
        for ans in answers:
            word_count = len(ans.text_answer.split()) if ans.text_answer else None
            result.append({
                "id": ans.id,
                "session_id": ans.session_id,
                "question_id": ans.question_id,
                "selected_option_ids": ans.selected_option_ids,
                "text_answer": ans.text_answer,
                "word_count": word_count,
                "image_answer_url": ans.image_answer_url,
                "thumbnail_url": ans.thumbnail_url,
                "answered_at": ans.answered_at
            })
        return result

    @staticmethod
    def submit_answer(db: Session, session_id: str, answer_in: AnswerSubmitRequest, current_user: User) -> Answer:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied")

        SessionService._validate_session_active_and_within_deadline(db, session)

        now = datetime.now(timezone.utc)
        session.last_activity_at = now

        # Find existing answer or create new
        existing = db.query(Answer).filter(
            Answer.session_id == session_id,
            Answer.question_id == answer_in.question_id
        ).first()
        if existing:
            existing.selected_option_ids = answer_in.selected_option_ids
            existing.text_answer = answer_in.text_answer
            existing.image_answer_url = answer_in.image_answer_url
            existing.answered_at = now
            answer_record = existing
        else:
            answer_record = Answer(
                session_id=session_id,
                question_id=answer_in.question_id,
                selected_option_ids=answer_in.selected_option_ids,
                text_answer=answer_in.text_answer,
                image_answer_url=answer_in.image_answer_url,
                answered_at=now
            )
            db.add(answer_record)

        db.commit()
        db.refresh(answer_record)
        return answer_record

    @staticmethod
    def record_proctor_event(db: Session, session_id: str, event_in: ProctorEventCreate, current_user: User) -> ProctorEvent:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied")

        SessionService._validate_session_active_and_within_deadline(db, session)

        now = datetime.now(timezone.utc)
        session.last_activity_at = now

        event = ProctorEvent(
            session_id=session_id,
            event_type=event_in.event_type,
            timestamp=now,
            payload=event_in.payload,
            severity=event_in.severity or "warning"
        )
        db.add(event)

        if event_in.event_type == ProctorEventType.TAB_SWITCH:
            session.tab_switch_count += 1
            exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
            if exam and exam.proctoring_settings:
                max_warnings = exam.proctoring_settings.get("max_tab_switch_warnings", 3)
                if session.tab_switch_count >= max_warnings:
                    session.is_flagged = True

        db.commit()
        db.refresh(event)
        return event

    @staticmethod
    def submit_exam_session(db: Session, session_id: str, current_user: User, auto_submit: bool = False) -> ExamSession:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied")

        if session.status in [SessionStatus.SUBMITTED, SessionStatus.AUTO_SUBMITTED, SessionStatus.TERMINATED]:
            raise BadRequestException(f"Session is already {session.status.value}")

        now = datetime.now(timezone.utc)
        session.status = SessionStatus.AUTO_SUBMITTED if auto_submit else SessionStatus.SUBMITTED
        session.submitted_reason = SubmittedReason.TIME_EXPIRED if auto_submit else SubmittedReason.MANUAL
        session.submitted_at = now
        session.last_activity_at = now

        db.commit()
        db.refresh(session)

        # Trigger auto-evaluation
        EvaluationService.evaluate_objective(db, session.id)

        return session
