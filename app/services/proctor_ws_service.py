from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from app.core.security import decode_jwt_token
from app.db.session import SessionLocal
from app.models import ExamSession, ProctorEvent, ProctorEventType, SessionStatus


_SIGNAL_TO_EVENT = {
    "gaze_away": ProctorEventType.GAZE_AWAY,
    "tab_switch": ProctorEventType.TAB_SWITCH,
    "multiple_faces": ProctorEventType.MULTIPLE_FACES,
    "no_face": ProctorEventType.NO_FACE,
    "window_blur": ProctorEventType.WINDOW_BLUR,
    "fullscreen_exit": ProctorEventType.FULLSCREEN_EXIT,
}

_SIGNAL_WEIGHTS = {
    ProctorEventType.GAZE_AWAY: 1.0,
    ProctorEventType.TAB_SWITCH: 1.5,
    ProctorEventType.MULTIPLE_FACES: 3.0,
    ProctorEventType.NO_FACE: 2.5,
    ProctorEventType.WINDOW_BLUR: 2.0,
    ProctorEventType.FULLSCREEN_EXIT: 2.0,
}


class ProctorWebSocketService:
    @staticmethod
    def _validate_token(session_id: str, token: str | None) -> str:
        if not token:
            raise ValueError("Missing token")
        payload = decode_jwt_token(token)
        if not payload or payload.get("type") != "session":
            raise ValueError("Invalid session token")
        if payload.get("session_id") != session_id:
            raise ValueError("Token is not bound to this session")
        return payload.get("sub")

    @staticmethod
    def _record_signal(session_id: str, student_id: str, message: dict[str, Any]) -> dict[str, Any]:
        db = SessionLocal()
        try:
            signal = str(message.get("signal", "")).strip().lower()
            severity = str(message.get("severity", "warning")).lower()
            payload = message.get("payload") or {}

            if signal not in _SIGNAL_TO_EVENT:
                raise ValueError("Unsupported proctor signal")

            session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
            if not session:
                raise ValueError("Session not found")
            if session.student_id != student_id:
                raise ValueError("Unauthorized session access")
            if session.status not in [SessionStatus.IN_PROGRESS, SessionStatus.FLAGGED]:
                raise ValueError("Session is not active")

            event_type = _SIGNAL_TO_EVENT[signal]
            now = datetime.now(timezone.utc)
            event = ProctorEvent(
                session_id=session.id,
                event_type=event_type,
                payload=payload,
                severity=severity,
                timestamp=now,
            )
            db.add(event)

            if event_type == ProctorEventType.TAB_SWITCH:
                session.tab_switch_count += 1

            recent_events = (
                db.query(ProctorEvent)
                .filter(ProctorEvent.session_id == session.id)
                .all()
            )
            suspicion_score = sum(_SIGNAL_WEIGHTS.get(ev.event_type, 0.0) for ev in recent_events) + (
                session.tab_switch_count * 0.5
            )
            if suspicion_score >= 8.0:
                session.is_flagged = True

            session.last_activity_at = now
            db.commit()

            return {
                "type": "ack",
                "signal": signal,
                "suspicion_score": round(suspicion_score, 2),
                "is_flagged": session.is_flagged,
                "server_time": now.isoformat(),
            }
        finally:
            db.close()

    @staticmethod
    async def handle_connection(websocket: WebSocket, session_id: str) -> None:
        token = websocket.query_params.get("token")
        try:
            student_id = ProctorWebSocketService._validate_token(session_id, token)
        except ValueError:
            await websocket.close(code=1008)
            return

        await websocket.accept()
        await websocket.send_json(
            {
                "type": "connected",
                "session_id": session_id,
                "server_time": datetime.now(timezone.utc).isoformat(),
            }
        )

        while True:
            try:
                message = await websocket.receive_json()
                msg_type = message.get("type")
                if msg_type == "ping":
                    await websocket.send_json(
                        {"type": "pong", "server_time": datetime.now(timezone.utc).isoformat()}
                    )
                    continue
                if msg_type != "signal":
                    await websocket.send_json({"type": "error", "error": "Unsupported message type"})
                    continue

                try:
                    response = ProctorWebSocketService._record_signal(
                        session_id=session_id,
                        student_id=student_id,
                        message=message,
                    )
                    await websocket.send_json(response)
                except ValueError as exc:
                    await websocket.send_json({"type": "error", "error": str(exc)})
            except Exception:
                await websocket.close()
                break
