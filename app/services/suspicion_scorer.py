from typing import List, Dict, Any
from app.models import ProctorEventType


DEFAULT_WEIGHTS = {
    ProctorEventType.NO_FACE: 10.0,
    ProctorEventType.MULTIPLE_FACES: 25.0,
    ProctorEventType.GAZE_AWAY: 5.0,
    ProctorEventType.TAB_SWITCH: 15.0,
    ProctorEventType.WINDOW_BLUR: 10.0,
    ProctorEventType.FULLSCREEN_EXIT: 15.0,
    ProctorEventType.HEARTBEAT_LOST: 15.0,
    ProctorEventType.CONCURRENT_SESSION: 30.0,
    ProctorEventType.IP_CHANGE: 10.0,
}

PER_SIGNAL_CAPS = {
    ProctorEventType.NO_FACE: 30.0,
    ProctorEventType.MULTIPLE_FACES: 50.0,
    ProctorEventType.GAZE_AWAY: 20.0,
    ProctorEventType.TAB_SWITCH: 45.0,
    ProctorEventType.WINDOW_BLUR: 20.0,
    ProctorEventType.FULLSCREEN_EXIT: 30.0,
    ProctorEventType.HEARTBEAT_LOST: 30.0,
    ProctorEventType.CONCURRENT_SESSION: 60.0,
    ProctorEventType.IP_CHANGE: 20.0,
}


def calculate_suspicion_score(
    events: List[Dict[str, Any]],
    weights: Dict[ProctorEventType, float] = None,
    proctoring_settings: Dict[str, Any] = None
) -> float:
    """
    Pure, deterministic function of weighted, severity-based event counts with per-signal caps.
    Returns a float score clamped strictly to [0.0, 100.0].
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    proctoring_settings = proctoring_settings or {}
    webcam_enabled = proctoring_settings.get("webcam_enabled", True)
    gaze_enabled = proctoring_settings.get("gaze_enabled", True)

    accumulated: Dict[ProctorEventType, float] = {ev_type: 0.0 for ev_type in DEFAULT_WEIGHTS}

    for ev in events:
        ev_type_raw = ev.get("event_type")
        if isinstance(ev_type_raw, str):
            try:
                ev_type = ProctorEventType(ev_type_raw)
            except ValueError:
                continue
        elif isinstance(ev_type_raw, ProctorEventType):
            ev_type = ev_type_raw
        else:
            continue

        # Respect settings: ignore webcam/gaze signals if disabled for exam
        if not webcam_enabled and ev_type in [ProctorEventType.NO_FACE, ProctorEventType.MULTIPLE_FACES, ProctorEventType.WEBCAM_SNAPSHOT]:
            continue
        if not gaze_enabled and ev_type == ProctorEventType.GAZE_AWAY:
            continue

        weight = weights.get(ev_type, 5.0)
        severity = ev.get("severity", "warning")
        severity_mult = 1.5 if severity == "high" else (2.0 if severity == "critical" else 1.0)

        accumulated[ev_type] = accumulated.get(ev_type, 0.0) + (weight * severity_mult)

    total_score = 0.0
    for ev_type, raw_subtotal in accumulated.items():
        cap = PER_SIGNAL_CAPS.get(ev_type, 100.0)
        subtotal = min(raw_subtotal, cap)
        total_score += subtotal

    return round(min(100.0, max(0.0, total_score)), 2)
