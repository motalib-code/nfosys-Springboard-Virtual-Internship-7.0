from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import QuestionBank, Option, User, UserRole, QuestionType, Difficulty
from app.schemas.question import QuestionCreate, QuestionUpdate
from app.core.exceptions import NotFoundException, PermissionDeniedException, BadRequestException


class QuestionService:
    @staticmethod
    def create_question(db: Session, question_in: QuestionCreate, current_user: User) -> QuestionBank:
        question = QuestionBank(
            created_by=current_user.id,
            question_type=question_in.question_type,
            subject=question_in.subject,
            tags=question_in.tags,
            difficulty=question_in.difficulty,
            question_text=question_in.question_text,
            image_url=question_in.image_url,
            marks=question_in.marks,
            negative_marks=question_in.negative_marks,
            model_answer=question_in.model_answer,
            expected_answer=question_in.expected_answer,
            max_marks_for_image=question_in.max_marks_for_image,
            is_active=True
        )
        db.add(question)
        db.flush()

        if question_in.options:
            for opt_in in question_in.options:
                option = Option(
                    question_id=question.id,
                    option_text=opt_in.option_text,
                    is_correct=opt_in.is_correct,
                    display_order=opt_in.display_order or 0
                )
                db.add(option)

        db.commit()
        db.refresh(question)
        return question

    @staticmethod
    def get_question(db: Session, question_id: str) -> QuestionBank:
        question = db.query(QuestionBank).filter(QuestionBank.id == question_id).first()
        if not question:
            raise NotFoundException("Question not found")
        return question

    @staticmethod
    def list_questions(
        db: Session,
        subject: Optional[str] = None,
        difficulty: Optional[Difficulty] = None,
        question_type: Optional[QuestionType] = None,
        tag: Optional[str] = None,
        page: int = 1,
        size: int = 20
    ) -> Tuple[List[QuestionBank], int]:
        query = db.query(QuestionBank).filter(QuestionBank.is_active == True)

        if subject:
            query = query.filter(QuestionBank.subject.ilike(f"%{subject}%"))
        if difficulty:
            query = query.filter(QuestionBank.difficulty == difficulty)
        if question_type:
            query = query.filter(QuestionBank.question_type == question_type)

        total = query.count()
        items = query.offset((page - 1) * size).limit(size).all()

        # Optional python-side filtering for tag if tag provided
        if tag:
            filtered_items = []
            for q in items:
                if q.tags and isinstance(q.tags, list) and tag in q.tags:
                    filtered_items.append(q)
            items = filtered_items

        return items, total

    @staticmethod
    def update_question(
        db: Session,
        question_id: str,
        question_in: QuestionUpdate,
        current_user: User
    ) -> QuestionBank:
        question = QuestionService.get_question(db, question_id)

        # Access check: Examiners can edit only their own questions; Admins can edit all
        if current_user.role != UserRole.ADMIN and question.created_by != current_user.id:
            raise PermissionDeniedException("You do not have permission to edit this question")

        update_data = question_in.model_dump(exclude_unset=True)

        options_data = update_data.pop("options", None)

        for field, value in update_data.items():
            setattr(question, field, value)

        # Validate negative_marks <= marks after update
        if question.negative_marks > question.marks:
            raise BadRequestException("negative_marks cannot exceed marks")

        if options_data is not None:
            # Re-create options
            db.query(Option).filter(Option.question_id == question.id).delete()
            for opt_dict in options_data:
                option = Option(
                    question_id=question.id,
                    option_text=opt_dict["option_text"],
                    is_correct=opt_dict.get("is_correct", False),
                    display_order=opt_dict.get("display_order", 0)
                )
                db.add(option)

        db.commit()
        db.refresh(question)
        return question

    @staticmethod
    def delete_question(db: Session, question_id: str, current_user: User) -> None:
        question = QuestionService.get_question(db, question_id)

        if current_user.role != UserRole.ADMIN and question.created_by != current_user.id:
            raise PermissionDeniedException("You do not have permission to delete this question")

        question.is_active = False
        db.commit()
