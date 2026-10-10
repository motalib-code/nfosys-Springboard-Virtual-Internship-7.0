import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, status
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.core.deps import get_db, get_current_user, require_role
from app.core.security import verify_token
from app.models import ExamSession, Exam, ProctorEvent, ProctorEventType, User, UserRole
from app.services.suspicion_scorer import calculate_suspicion_score
from app.core.exceptions import NotFoundException, PermissionDeniedException, BadRequestException
from app.schemas.session import ProctorEventOut

logger = logging.getLogger("proctoring")

router = APIRouter(tags=["Proctoring"])

# Bounded queue for non-blocking DB writes (lazy init per event loop)
_event_queue: Optional[asyncio.Queue] = None


def get_event_queue() -> asyncio.Queue:
    global _event_queue
    if _event_queue is None:
        _event_queue = asyncio.Queue(maxsize=1000)
    return _event_queue


async def bg_event_writer():
    q = get_event_queue()
    while True:
        try:
            item = await q.get()
            session_id, events_to_insert, updated_score, is_flagged = item

            db: Session = SessionLocal()
            try:
                # Batch insert events
                for ev_data in events_to_insert:
                    event = ProctorEvent(
                        session_id=session_id,
                        event_type=ev_data["event_type"],
                        timestamp=ev_data["timestamp"],
                        payload=ev_data.get("payload"),
                        severity=ev_data.get("severity", "warning")
                    )
                    db.add(event)

                # Update exam session
                session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
                if session:
                    session.suspicion_score = updated_score
                    if is_flagged:
                        session.is_flagged = True
                    # Snapshot score update in proctor_events
                    score_event = ProctorEvent(
                        session_id=session_id,
                        event_type=ProctorEventType.SCORE_UPDATE,
                        timestamp=datetime.now(timezone.utc),
                        payload={"suspicion_score": updated_score},
                        severity="info"
                    )
                    db.add(score_event)

                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Error in bg_event_writer: {e}")
            finally:
                db.close()
                q.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Unexpected queue error: {e}")


@router.post("/sessions/{id}/proctor/precheck")
def proctor_precheck(
    id: str,
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Precheck before starting exam: face presence must be verified.
    """
    session = db.query(ExamSession).filter(ExamSession.id == id).first()
    if not session:
        raise NotFoundException("Exam session not found")

    if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
        raise PermissionDeniedException("Access denied")

    face_present = payload.get("face_present", False)
    face_count = payload.get("face_count", 0)

    if not face_present or face_count < 1:
        raise BadRequestException("Face precheck failed: No face detected. Please position yourself in front of the camera.")

    return {"status": "passed", "message": "Proctoring precheck successful."}


@router.websocket("/ws/proctor/{session_id}")
async def proctor_websocket(websocket: WebSocket, session_id: str, token: str = Query(...)):
    await websocket.accept()

    # Authenticate token during handshake
    payload = verify_token(token, token_type="session")
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired session token")
        return

    student_id = payload.get("sub")
    exam_id = payload.get("exam_id")
    token_session_id = payload.get("session_id")
    jti = payload.get("jti")

    if token_session_id != session_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token session mismatch")
        return

    db: Session = SessionLocal()
    try:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session or session.student_id != student_id or session.exam_id != exam_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session invalid or student mismatch")
            return

        if session.active_token_jti and session.active_token_jti != jti:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session token superseded (jti mismatch)")
            return

        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        proctoring_settings = exam.proctoring_settings or {} if exam else {}
    finally:
        db.close()

    last_seq = -1
    recent_events: List[Dict[str, Any]] = []

    try:
        while True:
            try:
                data_text = await asyncio.wait_for(websocket.receive_text(), timeout=25.0)
                data = json.loads(data_text)
            except asyncio.TimeoutError:
                now = datetime.now(timezone.utc)
                lost_event = {
                    "event_type": ProctorEventType.HEARTBEAT_LOST,
                    "timestamp": now,
                    "payload": {"reason": "Heartbeat timeout (>25s)"},
                    "severity": "high"
                }
                recent_events.append(lost_event)
                score = calculate_suspicion_score(recent_events, proctoring_settings=proctoring_settings)
                is_flagged = score >= 70.0
                try:
                    await get_event_queue().put((session_id, [lost_event], score, is_flagged))
                except asyncio.QueueFull:
                    pass
                continue

            seq = data.get("seq", 0)
            if seq <= last_seq:
                continue
            last_seq = seq

            now = datetime.now(timezone.utc)
            events_to_insert = []
            warnings = []

            # 1. Face checks
            face_count = data.get("face_count", 1)
            face_present = data.get("face_present", True)

            if proctoring_settings.get("webcam_enabled", True):
                if not face_present:
                    events_to_insert.append({
                        "event_type": ProctorEventType.NO_FACE,
                        "timestamp": now,
                        "payload": {"seq": seq},
                        "severity": "high"
                    })
                    warnings.append("No face detected in camera feed.")
                elif face_count > 1:
                    events_to_insert.append({
                        "event_type": ProctorEventType.MULTIPLE_FACES,
                        "timestamp": now,
                        "payload": {"seq": seq, "face_count": face_count},
                        "severity": "critical"
                    })
                    warnings.append("Multiple faces detected.")

            # 2. Gaze checks
            gaze = data.get("gaze") or {}
            if proctoring_settings.get("gaze_enabled", True):
                if gaze.get("on_screen") is False:
                    events_to_insert.append({
                        "event_type": ProctorEventType.GAZE_AWAY,
                        "timestamp": now,
                        "payload": {"gaze": gaze},
                        "severity": "warning"
                    })
                    warnings.append("Off-screen gaze detected.")

            # 3. Browser signals
            if data.get("tab_visible") is False or data.get("window_focused") is False:
                events_to_insert.append({
                    "event_type": ProctorEventType.TAB_SWITCH,
                    "timestamp": now,
                    "payload": {"tab_visible": data.get("tab_visible"), "window_focused": data.get("window_focused")},
                    "severity": "warning"
                })
                warnings.append("Tab switched or window lost focus.")

            if data.get("fullscreen") is False:
                events_to_insert.append({
                    "event_type": ProctorEventType.FULLSCREEN_EXIT,
                    "timestamp": now,
                    "payload": {},
                    "severity": "warning"
                })

            discrete_event = data.get("event")
            if discrete_event:
                events_to_insert.append({
                    "event_type": discrete_event.get("event_type", ProctorEventType.TAB_SWITCH),
                    "timestamp": now,
                    "payload": discrete_event.get("payload"),
                    "severity": discrete_event.get("severity", "warning")
                })

            recent_events.extend(events_to_insert)
            score = calculate_suspicion_score(recent_events, proctoring_settings=proctoring_settings)
            is_flagged = score >= 70.0

            if events_to_insert:
                try:
                    await get_event_queue().put((session_id, events_to_insert, score, is_flagged))
                except asyncio.QueueFull:
                    pass

            if score >= 40.0 and score < 70.0:
                warnings.append("Suspicion score elevated. Please focus on your exam.")

            db_rem: Session = SessionLocal()
            seconds_remaining = 0
            try:
                sess_rem = db_rem.query(ExamSession).filter(ExamSession.id == session_id).first()
                if sess_rem and sess_rem.server_deadline:
                    diff = (sess_rem.server_deadline.replace(tzinfo=timezone.utc) - now).total_seconds()
                    seconds_remaining = max(0, int(diff))
            finally:
                db_rem.close()

            response_payload = {
                "ack": seq,
                "server_time": now.isoformat(),
                "seconds_remaining": seconds_remaining,
                "suspicion_score": score,
                "warnings": warnings
            }
            await websocket.send_json(response_payload)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error in session {session_id}: {e}")


@router.get("/exams/{id}/proctoring/sessions")
def get_exam_proctoring_sessions(
    id: str,
    flagged_only: bool = Query(False),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role([UserRole.EXAMINER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    """
    Keyset-paginated endpoint for examiners/admins to list exam sessions with suspicion scores.
    """
    query = db.query(ExamSession).filter(ExamSession.exam_id == id)
    if flagged_only:
        query = query.filter(ExamSession.is_flagged == True)

    if cursor:
        query = query.filter(ExamSession.id > cursor)

    sessions = query.order_by(ExamSession.created_at.desc(), ExamSession.id.asc()).limit(limit).all()
    return [
        {
            "session_id": s.id,
            "student_id": s.student_id,
            "status": s.status,
            "suspicion_score": s.suspicion_score,
            "is_flagged": s.is_flagged,
            "tab_switch_count": s.tab_switch_count,
            "created_at": s.created_at
        }
        for s in sessions
    ]


@router.get("/sessions/{id}/proctor-events", response_model=List[ProctorEventOut])
def get_session_proctor_events(
    id: str,
    current_user: User = Depends(require_role([UserRole.EXAMINER, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    """
    Retrieves the timeline of proctoring events for an exam session.
    """
    session = db.query(ExamSession).filter(ExamSession.id == id).first()
    if not session:
        raise NotFoundException("Exam session not found")

    events = db.query(ProctorEvent).filter(ProctorEvent.session_id == id).order_by(ProctorEvent.timestamp.asc()).all()
    return events
