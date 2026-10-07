from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import ExamSession, Exam, Answer, ProctorEvent, SessionStatus, User, UserRole, ProctorEventType
from app.schemas.session import AnswerSubmitRequest, ProctorEventCreate
from app.services.paper_generator import PaperGenerator
from app.core.exceptions import NotFoundException, PermissionDeniedException, BadRequestException


class SessionService:
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

        if session.status not in [SessionStatus.IN_PROGRESS, SessionStatus.FLAGGED]:
            raise BadRequestException(f"Cannot submit answer when session status is {session.status.value}")

        # Find existing answer or create new
        existing = db.query(Answer).filter(
            Answer.session_id == session_id,
            Answer.question_id == answer_in.question_id
        ).first()

        now = datetime.now(timezone.utc)
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

        now = datetime.now(timezone.utc)
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

        session.status = SessionStatus.AUTO_SUBMITTED if auto_submit else SessionStatus.SUBMITTED
        session.submitted_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(session)
        return session
