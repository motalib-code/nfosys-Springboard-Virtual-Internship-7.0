# AI Proctoring Client-Server WebSocket Contract & Reference Integration

This document defines the real-time AI proctoring protocol between the browser client (MediaPipe Face Landmarker / TF.js) and the FastAPI backend.

---

## 1. Connection Handshake & Authentication

- **Endpoint**: `WS /api/v1/ws/proctor/{session_id}?token=<session_token>`
- **Authentication**: The `token` query parameter must be a valid, short-lived session token issued by `POST /api/v1/exams/{id}/start` or refreshed via `POST /api/v1/sessions/{id}/heartbeat`.
- **Validation Rules**:
  1. The JWT claims must bind `student_id`, `exam_id`, and `session_id`.
  2. The `jti` in the token must match `exam_sessions.active_token_jti`.
  3. The session status must be `in_progress` or `flagged`.
  4. Connections failing authentication will be closed immediately with status code `4001` or `4003`.

---

## 2. Precheck Endpoint

Before starting the exam session, the client can verify webcam face presence:
- **`POST /api/v1/sessions/{session_id}/proctor/precheck`**
- **Payload**:
  ```json
  {
    "face_present": true,
    "face_count": 1,
    "snapshot_b64": "data:image/jpeg;base64,..."
  }
  ```
- **Response**: `200 OK` if valid; `400 Bad Request` if no face or multiple faces detected.

---

## 3. Client 10s Heartbeat Payload Shape

Every 10 seconds, the client sends a structured telemetry frame over the WebSocket:

```json
{
  "seq": 1,
  "client_ts": 1711800000.0,
  "face_count": 1,
  "face_present": true,
  "gaze": {
    "yaw": 0.05,
    "pitch": -0.02,
    "on_screen": true,
    "confidence": 0.95
  },
  "tab_visible": true,
  "window_focused": true,
  "fullscreen": true,
  "snapshot_b64": null
}
```

---

## 4. Discrete Real-Time Event Payload

In addition to the 10s periodic heartbeat, discrete proctoring events can be sent immediately when triggered:

```json
{
  "event_type": "tab_switch",
  "client_ts": 1711800010.0,
  "payload": {
    "reason": "visibility_change_hidden",
    "tab_switch_count": 3
  }
}
```

Supported discrete event types:
- `tab_switch`
- `window_blur`
- `fullscreen_exit`
- `multiple_faces`
- `no_face`
- `gaze_away`
- `webcam_snapshot`

---

## 5. Server Ack Response Shape

The server acknowledges heartbeats and discrete events with current timing and risk state:

```json
{
  "ack": true,
  "server_time": "2026-03-30T10:00:00.000Z",
  "seconds_remaining": 3590,
  "suspicion_score": 15.0,
  "warnings": [
    "Off-screen gaze detected"
  ]
}
```

---

## 6. Reference Client-Side Integration Snippet (MediaPipe + WebSockets)

```javascript
// Minimal browser reference implementation for MediaPipe + WS Proctoring
class ProctoringClient {
  constructor(sessionId, sessionToken, wsUrl = "ws://localhost:8000/api/v1/ws/proctor/") {
    this.sessionId = sessionId;
    this.sessionToken = sessionToken;
    this.wsUrl = `${wsUrl}${sessionId}?token=${sessionToken}`;
    this.seq = 0;
    this.ws = null;
    this.heartbeatTimer = null;
  }

  connect() {
    this.ws = new WebSocket(this.wsUrl);

    this.ws.onopen = () => {
      console.log("[Proctor] Connected to backend WS");
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      const response = JSON.parse(event.data);
      console.log("[Proctor] Ack received:", response);
      if (response.suspicion_score >= 40) {
        this.showWarningAlert(`Suspicion Score Warning: ${response.suspicion_score}`);
      }
    };

    this.ws.onclose = () => {
      console.warn("[Proctor] Connection closed");
      this.stopHeartbeat();
    };
  }

  startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      this.sendHeartbeat();
    }, 10000);
  }

  stopHeartbeat() {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
  }

  sendHeartbeat(telemetry = {}) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.seq += 1;
    const payload = {
      seq: this.seq,
      client_ts: Date.now() / 1000.0,
      face_count: telemetry.faceCount ?? 1,
      face_present: telemetry.facePresent ?? true,
      gaze: {
        yaw: telemetry.yaw ?? 0.0,
        pitch: telemetry.pitch ?? 0.0,
        on_screen: telemetry.onScreen ?? true,
        confidence: telemetry.confidence ?? 0.98
      },
      tab_visible: !document.hidden,
      window_focused: document.hasFocus(),
      fullscreen: !!document.fullscreenElement,
      snapshot_b64: telemetry.snapshotB64 || null
    };

    this.ws.send(JSON.stringify(payload));
  }

  sendDiscreteEvent(eventType, payloadData = {}) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    const eventMsg = {
      event_type: eventType,
      client_ts: Date.now() / 1000.0,
      payload: payloadData
    };
    this.ws.send(JSON.stringify(eventMsg));
  }

  showWarningAlert(msg) {
    console.warn("[PROCTOR ALERT]", msg);
  }
}

// Browser Event Listeners
document.addEventListener("visibilitychange", () => {
  if (document.hidden && window.proctorClient) {
    window.proctorClient.sendDiscreteEvent("tab_switch", { hidden: true });
  }
});
```
