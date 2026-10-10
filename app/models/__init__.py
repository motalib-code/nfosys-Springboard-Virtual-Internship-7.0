import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String, Text, Boolean, Integer, Float, DateTime, Enum as SQLEnum,
    ForeignKey, UniqueConstraint, CheckConstraint, JSON, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from app.models.enums import (
    UserRole, QuestionType, Difficulty, RandomizationMode,
    ExamStatus, SessionStatus, ProctorEventType, GradingStatus, SubmittedReason,
    GradingQueueStatus
)


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole, native_enum=False), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    questions_created: Mapped[List["QuestionBank"]] = relationship("QuestionBank", back_populates="creator")
    exams_created: Mapped[List["Exam"]] = relationship("Exam", back_populates="creator")
    exam_sessions: Mapped[List["ExamSession"]] = relationship("ExamSession", back_populates="student")


class QuestionBank(Base):
    __tablename__ = "question_bank"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    question_type: Mapped[QuestionType] = mapped_column(SQLEnum(QuestionType, native_enum=False), index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    tags: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    difficulty: Mapped[Difficulty] = mapped_column(SQLEnum(Difficulty, native_enum=False), index=True, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    marks: Mapped[float] = mapped_column(Float, nullable=False)
    negative_marks: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expected_answer: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    max_marks_for_image: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    creator: Mapped[Optional["User"]] = relationship("User", back_populates="questions_created")
    options: Mapped[List["Option"]] = relationship("Option", back_populates="question", cascade="all, delete-orphan")
    exam_questions: Mapped[List["ExamQuestion"]] = relationship("ExamQuestion", back_populates="question")
    answers: Mapped[List["Answer"]] = relationship("Answer", back_populates="question")

    __table_args__ = (
        CheckConstraint('negative_marks >= 0', name='check_negative_marks_non_negative'),
        CheckConstraint('negative_marks <= marks', name='check_negative_marks_lte_marks'),
        CheckConstraint('marks > 0', name='check_marks_positive'),
    )


class Option(Base):
    __tablename__ = "options"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("question_bank.id", ondelete="CASCADE"), index=True, nullable=False)
    option_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    question: Mapped["QuestionBank"] = relationship("QuestionBank", back_populates="options")


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    randomization_mode: Mapped[RandomizationMode] = mapped_column(SQLEnum(RandomizationMode, native_enum=False), default=RandomizationMode.NONE, nullable=False)
    negative_marking_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    selection_rules: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    proctoring_settings: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    status: Mapped[ExamStatus] = mapped_column(SQLEnum(ExamStatus, native_enum=False), default=ExamStatus.DRAFT, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    creator: Mapped[Optional["User"]] = relationship("User", back_populates="exams_created")
    exam_questions: Mapped[List["ExamQuestion"]] = relationship("ExamQuestion", back_populates="exam", cascade="all, delete-orphan")
    sessions: Mapped[List["ExamSession"]] = relationship("ExamSession", back_populates="exam")

    __table_args__ = (
        CheckConstraint('end_time > start_time', name='check_end_time_after_start_time'),
        CheckConstraint('duration_minutes > 0', name='check_duration_positive'),
    )


class ExamQuestion(Base):
    __tablename__ = "exam_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    exam_id: Mapped[str] = mapped_column(String(36), ForeignKey("exams.id", ondelete="CASCADE"), index=True, nullable=False)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("question_bank.id", ondelete="CASCADE"), index=True, nullable=False)
    marks_override: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    exam: Mapped["Exam"] = relationship("Exam", back_populates="exam_questions")
    question: Mapped["QuestionBank"] = relationship("QuestionBank", back_populates="exam_questions")

    __table_args__ = (
        UniqueConstraint("exam_id", "question_id", name="uq_exam_question"),
    )


class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    exam_id: Mapped[str] = mapped_column(String(36), ForeignKey("exams.id", ondelete="CASCADE"), index=True, nullable=False)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[SessionStatus] = mapped_column(SQLEnum(SessionStatus, native_enum=False), default=SessionStatus.NOT_STARTED, index=True, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    active_token_jti: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    client_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    paper_seed: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    generated_paper: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    tab_switch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    server_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_reason: Mapped[Optional[SubmittedReason]] = mapped_column(SQLEnum(SubmittedReason, native_enum=False), nullable=True)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    suspicion_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    exam: Mapped["Exam"] = relationship("Exam", back_populates="sessions")
    student: Mapped["User"] = relationship("User", back_populates="exam_sessions")
    answers: Mapped[List["Answer"]] = relationship("Answer", back_populates="session", cascade="all, delete-orphan")
    proctor_events: Mapped[List["ProctorEvent"]] = relationship("ProctorEvent", back_populates="session", cascade="all, delete-orphan")
    result: Mapped[Optional["Result"]] = relationship("Result", back_populates="session", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", name="uq_exam_student_session"),
    )


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("exam_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("question_bank.id", ondelete="CASCADE"), index=True, nullable=False)
    selected_option_ids: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    text_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_answer_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    marks_awarded: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    graded_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    graded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    session: Mapped["ExamSession"] = relationship("ExamSession", back_populates="answers")
    question: Mapped["QuestionBank"] = relationship("QuestionBank", back_populates="answers")

    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_session_question_answer"),
    )


class Result(Base):
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("exam_sessions.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    total_marks: Mapped[float] = mapped_column(Float, nullable=False)
    obtained_marks: Mapped[float] = mapped_column(Float, nullable=False)
    negative_deductions: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    percentage: Mapped[float] = mapped_column(Float, nullable=False)
    grading_status: Mapped[GradingStatus] = mapped_column(SQLEnum(GradingStatus, native_enum=False), default=GradingStatus.PENDING, index=True, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    session: Mapped["ExamSession"] = relationship("ExamSession", back_populates="result")


class AIEvaluation(Base):
    __tablename__ = "ai_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    answer_id: Mapped[str] = mapped_column(String(36), ForeignKey("answers.id", ondelete="CASCADE"), index=True, nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    suggested_score: Mapped[float] = mapped_column(Float, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    key_points_matched: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    key_points_missed: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="completed", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_usage: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    answer: Mapped["Answer"] = relationship("Answer")


class GradingQueue(Base):
    __tablename__ = "grading_queue"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    answer_id: Mapped[str] = mapped_column(String(36), ForeignKey("answers.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("exam_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    exam_id: Mapped[str] = mapped_column(String(36), ForeignKey("exams.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[GradingQueueStatus] = mapped_column(SQLEnum(GradingQueueStatus, native_enum=False), default=GradingQueueStatus.PENDING, index=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    claimed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    answer: Mapped["Answer"] = relationship("Answer")
    session: Mapped["ExamSession"] = relationship("ExamSession")
    exam: Mapped["Exam"] = relationship("Exam")

    __table_args__ = (
        Index("ix_grading_queue_exam_status_created_id", "exam_id", "status", "created_at", "id"),
    )


class GradingAuditLog(Base):
    __tablename__ = "grading_audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    answer_id: Mapped[str] = mapped_column(String(36), ForeignKey("answers.id", ondelete="CASCADE"), index=True, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    old_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    answer: Mapped["Answer"] = relationship("Answer")
    actor: Mapped["User"] = relationship("User")


class ProctorEvent(Base):
    __tablename__ = "proctor_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("exam_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    event_type: Mapped[ProctorEventType] = mapped_column(SQLEnum(ProctorEventType, native_enum=False), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True, nullable=False)
    payload: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    severity: Mapped[str] = mapped_column(String(50), default="warning", nullable=False)

    session: Mapped["ExamSession"] = relationship("ExamSession", back_populates="proctor_events")
