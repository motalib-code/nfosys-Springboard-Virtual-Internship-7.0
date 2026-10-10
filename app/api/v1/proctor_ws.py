import asyncio
import base64
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.core.security import decode_jwt_token
from app.models import ExamSession, Exam, ProctorEvent, ProctorEventType, SessionStatus
from app.services.storage import get_storage_backend
from app.services.suspicion_scorer import calculate_suspicion_score

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/ws", tags=["Proctoring WebSocket"])


async def batch_event_writer(queue: asyncio.Queue):
    while True:
        try:
            event_data = await queue.get()
            if event_data is None:
                break
            db = SessionLocal()
            try:
                session_id = event_data["session_id"]
                etype = event_data["event_type"]
                payload = event_data.get("payload")
                severity = event_data.get("severity", "warning")
                ts = event_data.get("timestamp", datetime.now(timezone.utc))

                event = ProctorEvent(
                    session_id=session_id,
                    event_type=etype,
                    timestamp=ts,
                    payload=payload,
                    severity=severity
                )
                db.add(event)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to persist proctor event in batch writer: {e}")
            finally:
                db.close()
                queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in batch_event_writer loop: {e}")


@ws_router.websocket("/proctor/{session_id}")
async def proctor_websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(...)
):
    # 1. Handshake Authentication
    payload = decode_jwt_token(token)
    if not payload or payload.get("type") != "session":
        await websocket.close(code=4001, reason="Invalid session token")
        return

    token_session_id = payload.get("session_id")
    token_jti = payload.get("jti")
    student_id = payload.get("sub")

    if token_session_id != session_id:
        await websocket.close(code=4001, reason="Token bound to different session")
        return

    db = SessionLocal()
    try:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session or session.student_id != student_id:
            await websocket.close(code=4001, reason="Session not found or user mismatch")
            return

        if session.active_token_jti and session.active_token_jti != token_jti:
            await websocket.close(code=4001, reason="Stale session token JTI")
            return

        if session.status not in [SessionStatus.IN_PROGRESS, SessionStatus.FLAGGED]:
            await websocket.close(code=4001, reason=f"Session is {session.status.value}")
            return

        exam = db.query(Exam).filter(Exam.id == session.exam_id).first()
        proctoring_settings = exam.proctoring_settings if (exam and exam.proctoring_settings) else {}
    finally:
        db.close()

    await websocket.accept()

    queue: asyncio.Queue = asyncio.Queue()
    writer_task = asyncio.create_task(batch_event_writer(queue))

    last_seq = 0
    last_heartbeat_time = time.time()
    gaze_away_timestamps: List[float] = []

    try:
        while True:
            raw_text = await websocket.receive_text()
            now_ts = time.time()
            now_dt = datetime.now(timezone.utc)
            last_heartbeat_time = now_ts

            try:
                data = json.loads(raw_text)
            except Exception:
                await websocket.send_json({"error": "Invalid JSON format"})
                continue

            seq = data.get("seq", 0)
            if seq <= last_seq and seq != 0:
                await websocket.send_json({"error": "Out of order or duplicate sequence number"})
                continue
            last_seq = seq

            # Process snapshot if provided
            snapshot_url = None
            snapshot_b64 = data.get("snapshot_b64")
            if snapshot_b64:
                try:
                    img_bytes = base64.b64decode(snapshot_b64)
                    storage = get_storage_backend()
                    snapshot_url = storage.save_file(img_bytes, f"snapshot_{seq}.png", subfolder="snapshots")
                except Exception as e:
                    logger.warning(f"Failed to process snapshot b64: {e}")

            # Signals evaluation
            webcam_enabled = proctoring_settings.get("webcam_enabled", True)
            gaze_enabled = proctoring_settings.get("gaze_tracking_enabled", True)

            face_count = data.get("face_count", 1)
            face_present = data.get("face_present", True)
            gaze = data.get("gaze", {})
            tab_visible = data.get("tab_visible", True)
            window_focused = data.get("window_focused", True)
            fullscreen = data.get("fullscreen", True)

            events_created = []

            if webcam_enabled:
                if face_count > 1:
                    ev_payload = {"face_count": face_count, "seq": seq}
                    if snapshot_url:
                        ev_payload["snapshot_url"] = snapshot_url
                    await queue.put({
                        "session_id": session_id,
                        "event_type": ProctorEventType.MULTIPLE_FACES,
                        "payload": ev_payload,
                        "severity": "high",
                        "timestamp": now_dt
                    })
                    events_created.append(ProctorEventType.MULTIPLE_FACES)

                if not face_present or face_count == 0:
                    ev_payload = {"face_count": face_count, "seq": seq}
                    if snapshot_url:
                        ev_payload["snapshot_url"] = snapshot_url
                    await queue.put({
                        "session_id": session_id,
                        "event_type": ProctorEventType.NO_FACE,
                        "payload": ev_payload,
                        "severity": "warning",
                        "timestamp": now_dt
                    })
                    events_created.append(ProctorEventType.NO_FACE)

            if gaze_enabled and isinstance(gaze, dict):
                if gaze.get("on_screen") is False:
                    gaze_away_timestamps.append(now_ts)
                    # Filter timestamps within 2 min window (120s)
                    gaze_away_timestamps = [t for t in gaze_away_timestamps if now_ts - t <= 120.0]
                    if len(gaze_away_timestamps) >= 5:
                        await queue.put({
                            "session_id": session_id,
                            "event_type": ProctorEventType.GAZE_AWAY,
                            "payload": {"gaze": gaze, "rolling_count": len(gaze_away_timestamps)},
                            "severity": "warning",
                            "timestamp": now_dt
                        })
                        events_created.append(ProctorEventType.GAZE_AWAY)

            if not tab_visible or not window_focused:
                await queue.put({
                    "session_id": session_id,
                    "event_type": ProctorEventType.WINDOW_BLUR,
                    "payload": {"tab_visible": tab_visible, "window_focused": window_focused},
                    "severity": "warning",
                    "timestamp": now_dt
                })
                events_created.append(ProctorEventType.WINDOW_BLUR)

            if not fullscreen:
                await queue.put({
                    "session_id": session_id,
                    "event_type": ProctorEventType.FULLSCREEN_EXIT,
                    "payload": {"fullscreen": fullscreen},
                    "severity": "warning",
                    "timestamp": now_dt
                })
                events_created.append(ProctorEventType.FULLSCREEN_EXIT)

            # Compute updated suspicion score
            db = SessionLocal()
            try:
                session_obj = db.query(ExamSession).filter(ExamSession.id == session_id).first()
                if session_obj:
                    events_list = db.query(ProctorEvent).filter(ProctorEvent.session_id == session_id).all()
                    score = calculate_suspicion_score(events_list, proctoring_settings, now=now_dt)
                    session_obj.suspicion_score = score
                    if score >= 70.0:
                        session_obj.is_flagged = True
                    session_obj.last_activity_at = now_dt
                    db.commit()

                    seconds_remaining = 0
                    if session_obj.server_deadline:
                        deadline = session_obj.server_deadline if session_obj.server_deadline.tzinfo is not None else session_obj.server_deadline.replace(tzinfo=timezone.utc)
                        seconds_remaining = max(0, int((deadline - now_dt).total_seconds()))

                    warnings = []
                    if score >= 40.0:
                        warnings.append("High suspicion score detected. Please stay focused on the exam.")

                    await websocket.send_json({
                        "ack": seq,
                        "server_time": now_dt.isoformat(),
                        "seconds_remaining": seconds_remaining,
                        "suspicion_score": score,
                        "warnings": warnings
                    })
            finally:
                db.close()

    except WebSocketDisconnect:
        logger.info(f"Proctoring WS disconnected for session {session_id}")
    finally:
        writer_task.cancel()
