import base64
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from app.models import ExamSession, Exam, ProctorEvent, User, UserRole
from app.schemas.session import ProctorPrecheckRequest
from app.core.exceptions import NotFoundException, PermissionDeniedException, BadRequestException


class ProctoringService:
    @staticmethod
    def proctor_precheck(db: Session, session_id: str, precheck_in: ProctorPrecheckRequest, current_user: User) -> dict:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied")

        if not precheck_in.face_present or precheck_in.face_count != 1:
            raise BadRequestException("Proctor precheck failed: Exactly 1 face must be clearly visible before starting the exam.")

        return {"success": True, "message": "Proctor precheck passed successfully"}

    @staticmethod
    def get_exam_proctoring_sessions(
        db: Session,
        exam_id: str,
        current_user: User,
        limit: int = 20,
        cursor: Optional[str] = None,
        flagged_only: bool = False
    ) -> dict:
        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        if not exam:
            raise NotFoundException("Exam not found")

        if current_user.role == UserRole.EXAMINER and exam.created_by != current_user.id:
            raise PermissionDeniedException("Only the exam creator or an admin can access proctoring session reports")
        elif current_user.role == UserRole.STUDENT:
            raise PermissionDeniedException("Access denied")

        query = db.query(ExamSession).options(joinedload(ExamSession.student)).filter(ExamSession.exam_id == exam_id)

        if flagged_only:
            query = query.filter(ExamSession.is_flagged == True)

        # Keyset pagination on (suspicion_score DESC, id DESC)
        if cursor:
            try:
                decoded = base64.b64decode(cursor.encode("utf-8")).decode("utf-8")
                score_str, last_id = decoded.split("::")
                last_score = float(score_str)
                query = query.filter(
                    (ExamSession.suspicion_score < last_score) |
                    ((ExamSession.suspicion_score == last_score) & (ExamSession.id < last_id))
                )
            except Exception:
                raise BadRequestException("Invalid pagination cursor")

        query = query.order_by(ExamSession.suspicion_score.desc(), ExamSession.id.desc())
        sessions = query.limit(limit + 1).all()

        next_cursor = None
        if len(sessions) > limit:
            next_item = sessions[limit]
            raw_cursor = f"{next_item.suspicion_score}::{next_item.id}"
            next_cursor = base64.b64encode(raw_cursor.encode("utf-8")).decode("utf-8")
            sessions = sessions[:limit]

        session_list = []
        for s in sessions:
            session_list.append({
                "session_id": s.id,
                "student_id": s.student_id,
                "student_name": s.student.name if s.student else "Unknown",
                "student_email": s.student.email if s.student else "Unknown",
                "status": s.status,
                "suspicion_score": s.suspicion_score,
                "is_flagged": s.is_flagged,
                "tab_switch_count": s.tab_switch_count,
                "started_at": s.started_at,
                "submitted_at": s.submitted_at
            })

        return {
            "sessions": session_list,
            "next_cursor": next_cursor
        }

    @staticmethod
    def get_session_proctor_events(db: Session, session_id: str, current_user: User) -> List[dict]:
        session = db.query(ExamSession).options(joinedload(ExamSession.exam)).filter(ExamSession.id == session_id).first()
        if not session:
            raise NotFoundException("Exam session not found")

        if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
            raise PermissionDeniedException("Access denied")

        if current_user.role == UserRole.EXAMINER and session.exam.created_by != current_user.id:
            raise PermissionDeniedException("Access denied to proctor events for another examiner's exam")

        events = db.query(ProctorEvent).filter(ProctorEvent.session_id == session_id).order_by(ProctorEvent.timestamp.asc()).all()

        result = []
        for ev in events:
            snapshot_url = None
            if ev.payload and isinstance(ev.payload, dict):
                snapshot_url = ev.payload.get("snapshot_url")

            result.append({
                "id": ev.id,
                "session_id": ev.session_id,
                "event_type": ev.event_type.value,
                "timestamp": ev.timestamp,
                "severity": ev.severity,
                "payload": ev.payload,
                "snapshot_url": snapshot_url
            })
        return result
