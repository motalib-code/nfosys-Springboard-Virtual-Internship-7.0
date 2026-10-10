import math
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.models import ProctorEvent, ProctorEventType

EVENT_WEIGHTS = {
    ProctorEventType.MULTIPLE_FACES: {"weight": 25.0, "cap": 50.0},
    ProctorEventType.HEARTBEAT_LOST: {"weight": 20.0, "cap": 40.0},
    ProctorEventType.NO_FACE: {"weight": 15.0, "cap": 40.0},
    ProctorEventType.FULLSCREEN_EXIT: {"weight": 15.0, "cap": 30.0},
    ProctorEventType.TAB_SWITCH: {"weight": 10.0, "cap": 30.0},
    ProctorEventType.WINDOW_BLUR: {"weight": 10.0, "cap": 30.0},
    ProctorEventType.GAZE_AWAY: {"weight": 10.0, "cap": 30.0},
    ProctorEventType.IP_CHANGE: {"weight": 20.0, "cap": 40.0},
    ProctorEventType.CONCURRENT_SESSION: {"weight": 30.0, "cap": 60.0},
}


def calculate_suspicion_score(
    events: List[ProctorEvent],
    proctoring_settings: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None
) -> float:
    if not events:
        return 0.0

    if now is None:
        now = datetime.now(timezone.utc)

    webcam_enabled = True
    gaze_enabled = True
    if proctoring_settings:
        webcam_enabled = proctoring_settings.get("webcam_enabled", True)
        gaze_enabled = proctoring_settings.get("gaze_tracking_enabled", True)

    accumulated = {}

    for event in events:
        etype = event.event_type
        if not webcam_enabled and etype in [ProctorEventType.MULTIPLE_FACES, ProctorEventType.NO_FACE, ProctorEventType.WEBCAM_SNAPSHOT]:
            continue
        if not gaze_enabled and etype == ProctorEventType.GAZE_AWAY:
            continue

        if etype not in EVENT_WEIGHTS:
            continue

        weight_config = EVENT_WEIGHTS[etype]
        base_weight = weight_config["weight"]

        event_time = event.timestamp if event.timestamp.tzinfo is not None else event.timestamp.replace(tzinfo=timezone.utc)
        age_seconds = max(0.0, (now - event_time).total_seconds())
        decay_factor = math.exp(-age_seconds / 600.0)

        weighted_val = base_weight * decay_factor
        accumulated[etype] = accumulated.get(etype, 0.0) + weighted_val

    total_score = 0.0
    for etype, val in accumulated.items():
        cap = EVENT_WEIGHTS[etype]["cap"]
        total_score += min(val, cap)

    return round(min(100.0, max(0.0, total_score)), 2)
