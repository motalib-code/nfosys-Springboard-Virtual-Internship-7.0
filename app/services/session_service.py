from typing import List, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.models import ExamSession, Exam, Answer, ProctorEvent, SessionStatus, User, UserRole, ProctorEventType, SubmittedReason
from app.schemas.session import AnswerSubmitRequest, ProctorEventCreate
from app.services.paper_generator import PaperGenerator
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
    def submit_answer(db: Session, session_id: str, answer_in: AnswerSubmitRequest, current_user: User) -> Answer:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied")

        SessionService._validate_session_active_and_within_deadline(db, session)

        now = datetime.now(timezone.utc)
        session.last_activity_at = now

        # Validate question belongs to generated paper
        question_id = answer_in.question_id
        if not session.generated_paper:
            # Trigger paper generation if absent
            SessionService.get_session_paper(db, session_id, current_user)

        paper_questions = session.generated_paper or []
        paper_q_ids = [q.get("question_id") or q.get("id") for q in paper_questions if isinstance(q, dict)]
        if question_id not in paper_q_ids:
            raise BadRequestException("Question is not part of this student's exam paper")

        # Get question details from DB
        from app.models import QuestionBank, QuestionType, Option
        q_obj = db.query(QuestionBank).filter(QuestionBank.id == question_id).first()
        if not q_obj:
            raise NotFoundException("Question not found")

        word_count = None

        if q_obj.question_type in [QuestionType.MCQ, QuestionType.MULTI_SELECT]:
            if answer_in.selected_option_ids is not None:
                valid_options = db.query(Option.id).filter(Option.question_id == question_id).all()
                valid_opt_ids = {opt[0] for opt in valid_options}
                for sel_id in answer_in.selected_option_ids:
                    if sel_id not in valid_opt_ids:
                        raise BadRequestException(f"Option {sel_id} does not belong to question {question_id}")

                if q_obj.question_type == QuestionType.MCQ and len(answer_in.selected_option_ids) > 1:
                    raise BadRequestException("MCQ questions allow only exactly 1 selected option")

        elif q_obj.question_type in [QuestionType.SHORT_ANSWER, QuestionType.LONG_ANSWER]:
            if answer_in.text_answer is not None:
                import re
                # Strip control characters
                clean_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', answer_in.text_answer).strip()
                words = clean_text.split()
                word_count = len(words)
                min_w = 1 if q_obj.question_type == QuestionType.SHORT_ANSWER else 1
                max_w = 150 if q_obj.question_type == QuestionType.SHORT_ANSWER else 1000
                if word_count < min_w or word_count > max_w:
                    raise BadRequestException(f"Word count ({word_count}) out of bounds [{min_w}, {max_w}]")
                answer_in.text_answer = clean_text

        # Upsert answer using row lock / unique constraint handling
        existing = db.query(Answer).filter(
            Answer.session_id == session_id,
            Answer.question_id == question_id
        ).first()

        if existing:
            if answer_in.selected_option_ids is not None:
                existing.selected_option_ids = answer_in.selected_option_ids
            if answer_in.text_answer is not None:
                existing.text_answer = answer_in.text_answer
            if answer_in.image_answer_url is not None:
                existing.image_answer_url = answer_in.image_answer_url
            existing.answered_at = now
            answer_record = existing
        else:
            answer_record = Answer(
                session_id=session_id,
                question_id=question_id,
                selected_option_ids=answer_in.selected_option_ids,
                text_answer=answer_in.text_answer,
                image_answer_url=answer_in.image_answer_url,
                answered_at=now
            )
            db.add(answer_record)

        db.commit()
        db.refresh(answer_record)

        # Attach dynamic word_count attribute for schema response
        setattr(answer_record, "word_count", word_count)
        return answer_record

    @staticmethod
    def get_student_answers(db: Session, session_id: str, current_user: User) -> List[Answer]:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied")

        return db.query(Answer).filter(Answer.session_id == session_id).all()

    @staticmethod
    def upload_image_answer(
        db: Session,
        session_id: str,
        question_id: str,
        file_bytes: bytes,
        filename: str,
        current_user: User
    ) -> Answer:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied")

        SessionService._validate_session_active_and_within_deadline(db, session)

        now = datetime.now(timezone.utc)
        session.last_activity_at = now

        # Max size check (e.g. 8 MB)
        max_size_bytes = 8 * 1024 * 1024
        if len(file_bytes) > max_size_bytes:
            raise BadRequestException("File size exceeds maximum allowed threshold (8 MB)")

        # MIME magic bytes check
        if file_bytes.startswith(b'\xff\xd8\xff'):
            mime = "image/jpeg"
        elif file_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
            mime = "image/png"
        elif file_bytes.startswith(b'RIFF') and file_bytes[8:12] == b'WEBP':
            mime = "image/webp"
        else:
            raise BadRequestException("Invalid file format. Only JPEG, PNG, and WebP are allowed.")

        # Save via storage backend
        from app.services.storage import storage_backend
        image_url, thumbnail_url = storage_backend.save_image(file_bytes, filename)

        # Upsert answer
        existing = db.query(Answer).filter(
            Answer.session_id == session_id,
            Answer.question_id == question_id
        ).first()

        if existing:
            existing.image_answer_url = image_url
            existing.thumbnail_url = thumbnail_url
            existing.answered_at = now
            answer_record = existing
        else:
            answer_record = Answer(
                session_id=session_id,
                question_id=question_id,
                image_answer_url=image_url,
                thumbnail_url=thumbnail_url,
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

        # Trigger objective evaluation
        from app.services.evaluator import evaluate_objective
        evaluate_objective(db, session.id)

        # Enqueue subjective answers into grading_queue
        from app.models import Answer, QuestionBank, QuestionType, GradingQueue, GradingQueueStatus
        answers = db.query(Answer).filter(Answer.session_id == session.id).all()
        for ans in answers:
            q = db.query(QuestionBank).filter(QuestionBank.id == ans.question_id).first()
            if q and q.question_type in [QuestionType.SHORT_ANSWER, QuestionType.LONG_ANSWER, QuestionType.IMAGE_UPLOAD]:
                existing_q = db.query(GradingQueue).filter(GradingQueue.answer_id == ans.id).first()
                if not existing_q:
                    q_item = GradingQueue(
                        answer_id=ans.id,
                        session_id=session.id,
                        exam_id=session.exam_id,
                        status=GradingQueueStatus.PENDING,
                        created_at=now,
                        updated_at=now
                    )
                    db.add(q_item)
        db.commit()

        return session
