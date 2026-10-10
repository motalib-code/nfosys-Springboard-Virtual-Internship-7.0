import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, status
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.core.security import decode_jwt_token
from app.models import ExamSession, Exam, ProctorEvent, ProctorEventType, User, UserRole
from app.services.suspicion_scorer import SuspicionScorer
from app.services.session_service import SessionService
from app.core.exceptions import NotFoundException, PermissionDeniedException, BadRequestException
from app.core.deps import get_db, get_current_user

router = APIRouter(tags=["AI Proctoring"])

# Active connections map: session_id -> WebSocket
active_connections: Dict[str, WebSocket] = {}

# Background event processing queue
event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

async def event_writer_worker():
    """Background queue worker for batch inserting proctor events without blocking WS loop."""
    while True:
        event_data = await event_queue.get()
        db = SessionLocal()
        try:
            session_id = event_data["session_id"]
            event_type = event_data["event_type"]
            payload = event_data.get("payload")
            severity = event_data.get("severity", "warning")

            ev = ProctorEvent(
                session_id=session_id,
                event_type=event_type,
                timestamp=datetime.now(timezone.utc),
                payload=payload,
                severity=severity
            )
            db.add(ev)
            db.commit()
        except Exception as e:
            db.rollback()
        finally:
            db.close()
            event_queue.task_done()

@router.websocket("/ws/proctor/{session_id}")
async def proctor_websocket(websocket: WebSocket, session_id: str, token: str = Query(...)):
    await websocket.accept()

    # Authenticate token during handshake
    payload = decode_jwt_token(token)
    if not payload or payload.get("type") != "session":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid session token")
        return

    student_id = payload.get("student_id") or payload.get("sub")
    token_session_id = payload.get("session_id")
    jti = payload.get("jti")

    db = SessionLocal()
    try:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session not found")
            return

        if session.student_id != student_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Student mismatch")
            return

        if token_session_id and token_session_id != session_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session ID mismatch")
            return

        if session.active_token_jti and jti and session.active_token_jti != jti:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Rotated token")
            return

        exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
        proctor_settings = exam.proctoring_settings if exam else {}
    finally:
        db.close()

    active_connections[session_id] = websocket
    last_seq = -1
    last_heartbeat_time = datetime.now(timezone.utc)

    try:
        while True:
            # Receive message from client with timeout to detect missed heartbeats (>25s)
            try:
                data_str = await asyncio.wait_for(websocket.receive_text(), timeout=25.0)
            except asyncio.TimeoutError:
                # Silence > 25s -> heartbeat_lost event
                event_queue.put_nowait({
                    "session_id": session_id,
                    "event_type": ProctorEventType.HEARTBEAT_LOST,
                    "severity": "high",
                    "payload": {"reason": "Heartbeat silence > 25 seconds"}
                })
                continue

            data = json.loads(data_str)
            seq = data.get("seq", 0)

            # Reject out-of-order/duplicate seq
            if seq <= last_seq:
                continue
            last_seq = seq

            now = datetime.now(timezone.utc)
            last_heartbeat_time = now

            # Extract signals & generate events
            events_to_write = []

            face_count = data.get("face_count", 1)
            if face_count == 0:
                events_to_write.append({
                    "session_id": session_id,
                    "event_type": ProctorEventType.NO_FACE,
                    "severity": "warning",
                    "payload": data
                })
            elif face_count > 1:
                events_to_write.append({
                    "session_id": session_id,
                    "event_type": ProctorEventType.MULTIPLE_FACES,
                    "severity": "high",
                    "payload": data
                })

            gaze = data.get("gaze", {})
            if gaze.get("on_screen") is False:
                events_to_write.append({
                    "session_id": session_id,
                    "event_type": ProctorEventType.GAZE_AWAY,
                    "severity": "warning",
                    "payload": gaze
                })

            if data.get("tab_visible") is False or data.get("window_focused") is False:
                events_to_write.append({
                    "session_id": session_id,
                    "event_type": ProctorEventType.TAB_SWITCH,
                    "severity": "warning",
                    "payload": {"tab_visible": data.get("tab_visible"), "window_focused": data.get("window_focused")}
                })

            # Put generated events into async queue
            for ev in events_to_write:
                event_queue.put_nowait(ev)

            # Recompute suspicion score
            db = SessionLocal()
            try:
                all_events = db.query(ProctorEvent.event_type, ProctorEvent.payload).filter(ProctorEvent.session_id == session_id).all()
                ev_dicts = [{"event_type": e[0], "payload": e[1]} for e in all_events]
                for new_e in events_to_write:
                    ev_dicts.append({"event_type": new_e["event_type"], "payload": new_e.get("payload")})

                score = SuspicionScorer.compute_score(ev_dicts, settings=proctor_settings)

                # Persist score to session
                sess = db.query(ExamSession).filter(ExamSession.id == session_id).first()
                if sess:
                    sess.suspicion_score = score
                    if score >= 70.0:
                        sess.is_flagged = True
                    db.commit()

                seconds_rem = 0
                if sess and sess.server_deadline:
                    deadline = sess.server_deadline if sess.server_deadline.tzinfo is not None else sess.server_deadline.replace(tzinfo=timezone.utc)
                    seconds_rem = max(0, int((deadline - now).total_seconds()))
            finally:
                db.close()

            warnings = []
            if score >= 40.0:
                warnings.append("Elevated suspicion score detected. Please maintain gaze on the screen.")

            # Send ack reply
            response = {
                "ack": seq,
                "server_time": now.isoformat(),
                "seconds_remaining": seconds_rem,
                "suspicion_score": score,
                "warnings": warnings
            }
            await websocket.send_json(response)

    except WebSocketDisconnect:
        pass
    finally:
        active_connections.pop(session_id, None)


@router.post("/sessions/{id}/proctor/precheck")
def proctor_precheck(
    id: str,
    face_present: bool = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not face_present:
        raise BadRequestException("Face precheck failed: No face detected in webcam feed.")
    return {"status": "passed", "message": "Face precheck verified successfully."}


@router.get("/exams/{id}/proctoring/sessions")
def list_exam_proctoring_sessions(
    id: str,
    flagged_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    exam = db.query(Exam).filter(Exam.id == id).first()
    if not exam:
        raise NotFoundException("Exam not found")

    if current_user.role == UserRole.STUDENT:
        raise PermissionDeniedException("Access denied")
    if current_user.role == UserRole.EXAMINER and exam.created_by != current_user.id:
        raise PermissionDeniedException("Access denied to another examiner's exam")

    query = db.query(ExamSession).filter(ExamSession.exam_id == id)
    if flagged_only:
        query = query.filter(ExamSession.is_flagged == True)

    sessions = query.order_by(ExamSession.suspicion_score.desc()).all()
    return [{
        "session_id": s.id,
        "student_id": s.student_id,
        "status": s.status,
        "suspicion_score": s.suspicion_score,
        "is_flagged": s.is_flagged,
        "tab_switch_count": s.tab_switch_count
    } for s in sessions]


@router.get("/sessions/{id}/proctor-events")
def get_session_proctor_events(
    id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = db.query(ExamSession).filter(ExamSession.id == id).first()
    if not session:
        raise NotFoundException("Session not found")

    exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
    if current_user.role == UserRole.STUDENT and session.student_id != current_user.id:
        raise PermissionDeniedException("Access denied")
    if current_user.role == UserRole.EXAMINER and exam.created_by != current_user.id:
        raise PermissionDeniedException("Access denied")

    events = db.query(ProctorEvent).filter(ProctorEvent.session_id == id).order_by(ProctorEvent.timestamp.asc()).all()
    return [{
        "id": e.id,
        "event_type": e.event_type,
        "timestamp": e.timestamp,
        "severity": e.severity,
        "payload": e.payload
    } for e in events]
