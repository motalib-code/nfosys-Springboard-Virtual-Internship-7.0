from typing import Optional, List, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import Exam, ExamQuestion, QuestionBank, User, UserRole, ExamStatus
from app.schemas.exam import ExamCreate, ExamUpdate
from app.core.exceptions import (
    NotFoundException, PermissionDeniedException, BadRequestException, ConflictException
)


class ExamService:
    @staticmethod
    def create_exam(db: Session, exam_in: ExamCreate, current_user: User) -> Exam:
        # Verify question bank satisfies selection rules if present
        ExamService.verify_selection_rules(db, exam_in.subject, exam_in.selection_rules)

        exam = Exam(
            created_by=current_user.id,
            title=exam_in.title,
            subject=exam_in.subject,
            duration_minutes=exam_in.duration_minutes,
            start_time=exam_in.start_time,
            end_time=exam_in.end_time,
            randomization_mode=exam_in.randomization_mode or ExamStatus.DRAFT,
            negative_marking_enabled=exam_in.negative_marking_enabled,
            selection_rules=exam_in.selection_rules,
            proctoring_settings=exam_in.proctoring_settings,
            status=ExamStatus.DRAFT
        )
        db.add(exam)
        db.flush()

        if exam_in.question_ids:
            for idx, q_id in enumerate(exam_in.question_ids):
                eq = ExamQuestion(
                    exam_id=exam.id,
                    question_id=q_id,
                    order_index=idx
                )
                db.add(eq)

        db.commit()
        db.refresh(exam)
        return exam

    @staticmethod
    def get_exam(db: Session, exam_id: str) -> Exam:
        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        if not exam:
            raise NotFoundException("Exam not found")
        return exam

    @staticmethod
    def list_exams(
        db: Session,
        subject: Optional[str] = None,
        status: Optional[ExamStatus] = None,
        page: int = 1,
        size: int = 20
    ) -> Tuple[List[Exam], int]:
        query = db.query(Exam)
        if subject:
            query = query.filter(Exam.subject.ilike(f"%{subject}%"))
        if status:
            query = query.filter(Exam.status == status)

        total = query.count()
        items = query.offset((page - 1) * size).limit(size).all()
        return items, total

    @staticmethod
    def update_exam(db: Session, exam_id: str, exam_in: ExamUpdate, current_user: User) -> Exam:
        exam = ExamService.get_exam(db, exam_id)

        # Access check
        if current_user.role != UserRole.ADMIN and exam.created_by != current_user.id:
            raise PermissionDeniedException("You do not have permission to edit this exam")

        now = datetime.now(timezone.utc)
        start_t = exam.start_time.replace(tzinfo=timezone.utc) if exam.start_time.tzinfo is None else exam.start_time

        # Constraint: no edits to a published exam after it has started
        if exam.status == ExamStatus.PUBLISHED and now >= start_t:
            raise BadRequestException("Cannot edit a published exam that has already started")

        update_data = exam_in.model_dump(exclude_unset=True)
        question_ids = update_data.pop("question_ids", None)

        start_time = update_data.get("start_time", exam.start_time)
        end_time = update_data.get("end_time", exam.end_time)
        duration_minutes = update_data.get("duration_minutes", exam.duration_minutes)

        if end_time <= start_time:
            raise BadRequestException("end_time must be strictly after start_time")

        window_minutes = (end_time - start_time).total_seconds() / 60.0
        if duration_minutes > window_minutes:
            raise BadRequestException("duration_minutes cannot exceed total time window length")

        subject = update_data.get("subject", exam.subject)
        selection_rules = update_data.get("selection_rules", exam.selection_rules)
        ExamService.verify_selection_rules(db, subject, selection_rules)

        for field, value in update_data.items():
            setattr(exam, field, value)

        if question_ids is not None:
            db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).delete()
            for idx, q_id in enumerate(question_ids):
                eq = ExamQuestion(
                    exam_id=exam.id,
                    question_id=q_id,
                    order_index=idx
                )
                db.add(eq)

        db.commit()
        db.refresh(exam)
        return exam

    @staticmethod
    def publish_exam(db: Session, exam_id: str, current_user: User) -> Exam:
        exam = ExamService.get_exam(db, exam_id)

        if current_user.role != UserRole.ADMIN and exam.created_by != current_user.id:
            raise PermissionDeniedException("You do not have permission to publish this exam")

        # Verify selection rules before publishing
        ExamService.verify_selection_rules(db, exam.subject, exam.selection_rules)

        exam.status = ExamStatus.PUBLISHED
        db.commit()
        db.refresh(exam)
        return exam

    @staticmethod
    def delete_exam(db: Session, exam_id: str, current_user: User) -> None:
        exam = ExamService.get_exam(db, exam_id)

        if current_user.role != UserRole.ADMIN and exam.created_by != current_user.id:
            raise PermissionDeniedException("You do not have permission to delete this exam")

        db.delete(exam)
        db.commit()

    @staticmethod
    def verify_selection_rules(db: Session, subject: str, selection_rules: Optional[dict]) -> None:
        if not selection_rules:
            return

        bank_questions = db.query(QuestionBank).filter(
            QuestionBank.subject == subject,
            QuestionBank.is_active == True
        ).all()

        difficulty_rules = selection_rules.get("difficulty", selection_rules.get("counts_per_difficulty", {}))
        type_rules = selection_rules.get("question_type", selection_rules.get("counts_per_type", {}))

        if difficulty_rules:
            by_diff = {}
            for q in bank_questions:
                diff_val = q.difficulty.value if hasattr(q.difficulty, 'value') else str(q.difficulty)
                by_diff.setdefault(diff_val, 0)
                by_diff[diff_val] += 1

            for diff_key, req_count in difficulty_rules.items():
                avail = by_diff.get(diff_key, 0)
                if avail < req_count:
                    raise ConflictException(
                        f"Insufficient active questions for difficulty '{diff_key}' in subject '{subject}'. "
                        f"Required: {req_count}, Available: {avail}"
                    )

        if type_rules:
            by_type = {}
            for q in bank_questions:
                type_val = q.question_type.value if hasattr(q.question_type, 'value') else str(q.question_type)
                by_type.setdefault(type_val, 0)
                by_type[type_val] += 1

            for type_key, req_count in type_rules.items():
                avail = by_type.get(type_key, 0)
                if avail < req_count:
                    raise ConflictException(
                        f"Insufficient active questions for question type '{type_key}' in subject '{subject}'. "
                        f"Required: {req_count}, Available: {avail}"
                    )
