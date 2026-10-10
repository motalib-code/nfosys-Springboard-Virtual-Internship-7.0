# AI Proctoring Message Contract & Client Reference Guide

This document defines the WebSocket communication contract and client-side integration guidelines for the AI Proctoring Engine.

---

## 1. WebSocket Connection & Handshake

**Endpoint**:
`WS /api/v1/ws/proctor/{session_id}?token=<SESSION_TOKEN>`

### Authentication
- Pass the short-lived candidate session token returned from `POST /api/v1/exams/{id}/start` as a `token` URL query parameter.
- The server validates:
  1. JWT signature and expiration.
  2. Token type equals `session`.
  3. `session_id` in token matches `{session_id}` path parameter.
  4. Token `jti` matches `active_token_jti` on `exam_sessions`.
  5. Session status is `in_progress` or `flagged`.
- Connections failing validation are closed with code `4001`.

---

## 2. Client Heartbeat Payload Format

The browser client sends structured proctoring telemetry every 10 seconds.

```json
{
  "seq": 101,
  "client_ts": "2026-03-30T12:00:00Z",
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
  "snapshot_b64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
}
```

### Field Specifications
- `seq` (integer): Monotonically increasing sequence number per connection (must be strictly > previous `seq`).
- `client_ts` (string): ISO 8601 UTC timestamp.
- `face_count` (integer): Detected faces count from MediaPipe / FaceMesh.
- `face_present` (boolean): `true` if at least 1 candidate face is visible.
- `gaze` (object): Head pose & gaze tracking angles and `on_screen` flag.
- `tab_visible` (boolean): `document.visibilityState === 'visible'`.
- `window_focused` (boolean): `document.hasFocus()`.
- `fullscreen` (boolean): `Boolean(document.fullscreenElement)`.
- `snapshot_b64` (string, optional): Base64 PNG/JPEG webcam frame (throttled).

---

## 3. Server Response Format

The server responds immediately to every heartbeat frame.

```json
{
  "ack": 101,
  "server_time": "2026-03-30T12:00:01Z",
  "seconds_remaining": 1745,
  "suspicion_score": 15.0,
  "warnings": [
    "High suspicion score detected. Please stay focused on the exam."
  ]
}
```

---

## 4. Reference JavaScript Integration Snippet

Below is a reference JavaScript implementation for browser clients using MediaPipe / TensorFlow.js:

```javascript
class ProctorClient {
  constructor(sessionId, sessionToken) {
    this.sessionId = sessionId;
    this.token = sessionToken;
    this.seq = 0;
    this.ws = null;
    this.heartbeatTimer = null;
  }

  connect() {
    const wsUrl = `ws://${window.location.host}/api/v1/ws/proctor/${this.sessionId}?token=${encodeURIComponent(this.token)}`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log("[Proctoring] Connected to server.");
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      const response = JSON.parse(event.data);
      console.log("[Proctoring] ACK received:", response);
      if (response.warnings && response.warnings.length > 0) {
        response.warnings.forEach(w => alert(`[Proctor Warning]: ${w}`));
      }
    };

    this.ws.onclose = (e) => {
      console.warn("[Proctoring] Connection closed:", e.code, e.reason);
      this.stopHeartbeat();
    };
  }

  startHeartbeat() {
    this.heartbeatTimer = setInterval(() => this.sendTelemetry(), 10000);
  }

  stopHeartbeat() {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
  }

  sendTelemetry() {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    this.seq += 1;
    const payload = {
      seq: this.seq,
      client_ts: new Date().toISOString(),
      face_count: window.currentFaceCount || 1,
      face_present: window.currentFacePresent ?? true,
      gaze: {
        yaw: 0.0,
        pitch: 0.0,
        on_screen: window.currentGazeOnScreen ?? true,
        confidence: 0.95
      },
      tab_visible: document.visibilityState === 'visible',
      window_focused: document.hasFocus(),
      fullscreen: Boolean(document.fullscreenElement),
      snapshot_b64: window.captureWebcamFrameB64 ? window.captureWebcamFrameB64() : null
    };

    this.ws.send(JSON.stringify(payload));
  }
}

// Usage Example:
// const proctor = new ProctorClient("SESSION_ID_123", "JWT_SESSION_TOKEN");
// proctor.connect();
```
