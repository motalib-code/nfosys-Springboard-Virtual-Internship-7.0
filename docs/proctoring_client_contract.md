# Client-Side Proctoring Signal Contract

## WebSocket Endpoint
`WS /api/v1/ws/proctor/{session_id}?token=<session_access_token>`

## Client Heartbeat Payload (Sent every 10 seconds)
```json
{
  "seq": 1,
  "client_ts": "2026-03-30T10:00:00Z",
  "face_count": 1,
  "face_present": true,
  "gaze": {
    "yaw": 0.02,
    "pitch": -0.01,
    "on_screen": true,
    "confidence": 0.95
  },
  "tab_visible": true,
  "window_focused": true,
  "fullscreen": true,
  "snapshot_b64": null
}
```

## Server Response Payload
```json
{
  "ack": 1,
  "server_time": "2026-03-30T10:00:00.123456+00:00",
  "seconds_remaining": 1799,
  "suspicion_score": 0.0,
  "warnings": []
}
```

## Reference JavaScript Client Implementation (MediaPipe / TF.js)
```javascript
const socket = new WebSocket(`ws://localhost:8000/api/v1/ws/proctor/${sessionId}?token=${sessionToken}`);
let sequence = 1;

socket.onopen = () => {
  console.log("Proctoring WS Connected");
  setInterval(sendHeartbeat, 10000);
};

socket.onmessage = (event) => {
  const response = JSON.parse(event.data);
  console.log("Server Ack:", response);
  if (response.warnings && response.warnings.length > 0) {
    alert(response.warnings.join("\n"));
  }
};

function sendHeartbeat() {
  const payload = {
    seq: sequence++,
    client_ts: new Date().toISOString(),
    face_count: 1, // Computed via MediaPipe Face Detection
    face_present: true,
    gaze: { yaw: 0.0, pitch: 0.0, on_screen: true, confidence: 0.98 },
    tab_visible: !document.hidden,
    window_focused: document.hasFocus(),
    fullscreen: !!document.fullscreenElement
  };
  socket.send(JSON.stringify(payload));
}
```
