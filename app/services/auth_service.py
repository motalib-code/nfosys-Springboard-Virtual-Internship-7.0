from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.models import User, UserRole, Exam, ExamSession, SessionStatus, ExamStatus, ProctorEvent, ProctorEventType
from app.schemas.auth import UserRegister, UserLogin
from app.core.security import (
    get_password_hash, verify_password, create_access_token,
    create_refresh_token, create_exam_access_token, create_session_token,
    decode_jwt_token
)
from app.core.exceptions import (
    BadRequestException, CredentialsException, NotFoundException,
    PermissionDeniedException, ConflictException
)


class AuthService:
    @staticmethod
    def register_user(db: Session, user_in: UserRegister, current_user: User = None) -> User:
        # Check if requesting role is privileged (admin/examiner)
        if user_in.role in [UserRole.ADMIN, UserRole.EXAMINER]:
            if not current_user or current_user.role != UserRole.ADMIN:
                raise PermissionDeniedException("Only admins can register examiner or admin users.")

        # Check existing user
        existing = db.query(User).filter(User.email == user_in.email).first()
        if existing:
            raise BadRequestException("User with this email already exists.")

        hashed_pwd = get_password_hash(user_in.password)
        user = User(
            name=user_in.name,
            email=user_in.email,
            password_hash=hashed_pwd,
            role=user_in.role or UserRole.STUDENT,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def authenticate_user(db: Session, login_in: UserLogin) -> dict:
        user = db.query(User).filter(User.email == login_in.email).first()
        if not user or not verify_password(login_in.password, user.password_hash):
            raise CredentialsException("Invalid email or password.")
        if not user.is_active:
            raise CredentialsException("User account is inactive.")

        access_token = create_access_token(user.id, user.role.value)
        refresh_token = create_refresh_token(user.id, user.role.value)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    @staticmethod
    def refresh_access_token(db: Session, refresh_token: str) -> dict:
        payload = decode_jwt_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise CredentialsException("Invalid refresh token")

        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise CredentialsException("User inactive or not found")

        access_token = create_access_token(user.id, user.role.value)
        return {
            "access_token": access_token,
            "token_type": "bearer"
        }

    @staticmethod
    def issue_exam_access_token(db: Session, exam_id: str, current_user: User, student_id: str = None) -> str:
        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        if not exam:
            raise NotFoundException("Exam not found")

        target_student_id = current_user.id
        if current_user.role in [UserRole.ADMIN, UserRole.EXAMINER]:
            if student_id:
                target_student_id = student_id
        elif current_user.role == UserRole.STUDENT:
            if exam.status != ExamStatus.PUBLISHED:
                raise BadRequestException("Exam is not published")
            now = datetime.now(timezone.utc)
            start = exam.start_time.replace(tzinfo=timezone.utc) if exam.start_time.tzinfo is None else exam.start_time
            end = exam.end_time.replace(tzinfo=timezone.utc) if exam.end_time.tzinfo is None else exam.end_time
            if now < start or now > end:
                raise BadRequestException("Exam is outside the allowed time window")

        return create_exam_access_token(target_student_id, exam_id)

    @staticmethod
    def start_exam(db: Session, exam_id: str, exam_access_token: str, current_user: User, client_ip: str, user_agent: str) -> dict:
        payload = decode_jwt_token(exam_access_token)
        if not payload or payload.get("type") != "exam_access":
            raise CredentialsException("Invalid or expired exam access token")

        token_student_id = payload.get("student_id")
        token_exam_id = payload.get("exam_id")

        if token_student_id != current_user.id or token_exam_id != exam_id:
            raise PermissionDeniedException("Exam access token bound to a different student or exam")

        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        if not exam:
            raise NotFoundException("Exam not found")

        now = datetime.now(timezone.utc)
        start = exam.start_time.replace(tzinfo=timezone.utc) if exam.start_time.tzinfo is None else exam.start_time
        end = exam.end_time.replace(tzinfo=timezone.utc) if exam.end_time.tzinfo is None else exam.end_time
        if now < start or now > end:
            raise BadRequestException("Exam time window is invalid or expired")

        # Get or create session
        session = db.query(ExamSession).filter(
            ExamSession.exam_id == exam_id,
            ExamSession.student_id == current_user.id
        ).first()

        if not session:
            session = ExamSession(
                exam_id=exam_id,
                student_id=current_user.id,
                status=SessionStatus.IN_PROGRESS,
                started_at=now,
                client_ip=client_ip,
                user_agent=user_agent
            )
            db.add(session)
            db.flush()
        else:
            if session.status not in [SessionStatus.NOT_STARTED, SessionStatus.IN_PROGRESS]:
                raise ConflictException(f"Session already in {session.status.value} state")
            session.status = SessionStatus.IN_PROGRESS
            session.client_ip = client_ip
            session.user_agent = user_agent
            if not session.started_at:
                session.started_at = now

        # Create session token
        session_token = create_session_token(session.id, current_user.id, exam_id)
        session_payload = decode_jwt_token(session_token)
        session.active_token_jti = session_payload.get("jti")

        db.commit()
        db.refresh(session)

        return {
            "session_id": session.id,
            "session_token": session_token,
            "token_type": "bearer"
        }

    @staticmethod
    def process_heartbeat(db: Session, session_id: str, raw_token: str, current_user: User, client_ip: str, user_agent: str) -> dict:
        payload = decode_jwt_token(raw_token)
        if not payload or payload.get("type") != "session":
            raise CredentialsException("Invalid session token")

        token_jti = payload.get("jti")
        token_student_id = payload.get("sub")
        token_session_id = payload.get("session_id")

        if token_session_id != session_id or token_student_id != current_user.id:
            raise PermissionDeniedException("Session token bound to another session or user")

        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        # Active token JTI enforcement
        if session.active_token_jti and session.active_token_jti != token_jti:
            raise CredentialsException("Old or invalid session token. Concurrent login detected.")

        # Check IP or User Agent changes
        if (session.client_ip and session.client_ip != client_ip) or (session.user_agent and session.user_agent != user_agent):
            session.is_flagged = True
            proctor_event = ProctorEvent(
                session_id=session.id,
                event_type=ProctorEventType.WINDOW_BLUR,
                timestamp=datetime.now(timezone.utc),
                payload={
                    "reason": "IP or User-Agent changed during active session",
                    "old_ip": session.client_ip,
                    "new_ip": client_ip,
                    "old_ua": session.user_agent,
                    "new_ua": user_agent,
                },
                severity="high"
            )
            db.add(proctor_event)

        session.client_ip = client_ip
        session.user_agent = user_agent

        # Re-issue a fresh session token and rotate active_token_jti
        fresh_session_token = create_session_token(session.id, current_user.id, session.exam_id)
        fresh_payload = decode_jwt_token(fresh_session_token)
        session.active_token_jti = fresh_payload.get("jti")

        db.commit()

        return {
            "session_token": fresh_session_token,
            "is_flagged": session.is_flagged,
            "status": session.status.value
        }
