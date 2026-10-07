import hashlib
import random
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models import Exam, QuestionBank, User, Option, QuestionType, Difficulty
from app.core.config import settings
from app.core.exceptions import ConflictException


class PaperGenerator:
    @staticmethod
    def generate_paper_seed(exam_id: str, student_id: str) -> str:
        raw_str = f"{exam_id}:{student_id}:{settings.SERVER_SECRET}"
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_paper(db: Session, exam: Exam, student_id: str) -> Dict[str, Any]:
        seed = PaperGenerator.generate_paper_seed(exam.id, student_id)
        rng = random.Random(seed)

        bank_questions = db.query(QuestionBank).filter(
            QuestionBank.subject == exam.subject,
            QuestionBank.is_active == True
        ).all()

        selection_rules = exam.selection_rules or {}
        difficulty_rules = selection_rules.get("difficulty", selection_rules.get("counts_per_difficulty", {}))
        type_rules = selection_rules.get("question_type", selection_rules.get("counts_per_type", {}))

        selected_questions: List[QuestionBank] = []
        selected_ids = set()

        if difficulty_rules or type_rules:
            # 1. Filter candidates by difficulty rules if present
            candidates = list(bank_questions)
            if difficulty_rules:
                by_diff: Dict[str, List[QuestionBank]] = {}
                for q in candidates:
                    diff_val = q.difficulty.value if hasattr(q.difficulty, 'value') else str(q.difficulty)
                    by_diff.setdefault(diff_val, []).append(q)

                diff_selected = []
                for diff_key, req_count in difficulty_rules.items():
                    avail = by_diff.get(diff_key, [])
                    if len(avail) < req_count:
                        raise ConflictException(
                            f"Insufficient active questions for difficulty '{diff_key}' in subject '{exam.subject}'. "
                            f"Required: {req_count}, Available: {len(avail)}"
                        )
                    avail.sort(key=lambda x: x.id)
                    chosen = rng.sample(avail, req_count)
                    diff_selected.extend(chosen)
                candidates = diff_selected

            # 2. Filter / sample by type rules if present
            if type_rules:
                by_type: Dict[str, List[QuestionBank]] = {}
                for q in candidates:
                    type_val = q.question_type.value if hasattr(q.question_type, 'value') else str(q.question_type)
                    by_type.setdefault(type_val, []).append(q)

                type_selected = []
                for type_key, req_count in type_rules.items():
                    avail = by_type.get(type_key, [])
                    if len(avail) < req_count:
                        raise ConflictException(
                            f"Insufficient active questions for question type '{type_key}' in subject '{exam.subject}'. "
                            f"Required: {req_count}, Available: {len(avail)}"
                        )
                    avail.sort(key=lambda x: x.id)
                    chosen = rng.sample(avail, req_count)
                    type_selected.extend(chosen)
                candidates = type_selected

            selected_questions = candidates
        else:
            from app.models import ExamQuestion
            eq_records = db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).order_by(ExamQuestion.order_index).all()
            for eq in eq_records:
                q = db.query(QuestionBank).filter(QuestionBank.id == eq.question_id).first()
                if q:
                    selected_questions.append(q)

        rng.shuffle(selected_questions)

        paper_questions = []
        for q in selected_questions:
            options_list = []
            if q.options:
                opts = list(q.options)
                opts.sort(key=lambda o: o.id)
                rng.shuffle(opts)
                for opt in opts:
                    options_list.append({
                        "id": opt.id,
                        "option_text": opt.option_text,
                        "display_order": opt.display_order
                    })

            paper_questions.append({
                "question_id": q.id,
                "question_type": q.question_type.value if hasattr(q.question_type, 'value') else str(q.question_type),
                "question_text": q.question_text,
                "marks": q.marks,
                "negative_marks": q.negative_marks if exam.negative_marking_enabled else 0.0,
                "image_url": q.image_url,
                "options": options_list
            })

        return {
            "seed": seed,
            "questions": paper_questions
        }
