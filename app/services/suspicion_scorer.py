from typing import List, Dict, Any
from app.models import ProctorEventType

class SuspicionScorer:
    # Signal Weights (Configurable)
    WEIGHTS = {
        ProctorEventType.NO_FACE: 15.0,
        ProctorEventType.GAZE_AWAY: 8.0,
        ProctorEventType.MULTIPLE_FACES: 25.0,
        ProctorEventType.TAB_SWITCH: 10.0,
        ProctorEventType.WINDOW_BLUR: 5.0,
        ProctorEventType.FULLSCREEN_EXIT: 12.0,
        ProctorEventType.HEARTBEAT_LOST: 10.0,
        ProctorEventType.CONCURRENT_SESSION: 30.0,
        ProctorEventType.IP_CHANGE: 15.0
    }

    # Signal Caps (Limits max cumulative contribution per signal type)
    CAPS = {
        ProctorEventType.NO_FACE: 45.0,
        ProctorEventType.GAZE_AWAY: 32.0,
        ProctorEventType.MULTIPLE_FACES: 50.0,
        ProctorEventType.TAB_SWITCH: 40.0,
        ProctorEventType.WINDOW_BLUR: 20.0,
        ProctorEventType.FULLSCREEN_EXIT: 36.0,
        ProctorEventType.HEARTBEAT_LOST: 30.0,
        ProctorEventType.CONCURRENT_SESSION: 60.0,
        ProctorEventType.IP_CHANGE: 30.0
    }

    @staticmethod
    def compute_score(events: List[Dict[str, Any]], settings: Dict[str, Any] = None) -> float:
        """
        Pure, deterministic calculation of suspicion score (0.0 to 100.0) based on weighted,
        capped event signals. Respects proctoring_settings toggles.
        """
        if not events:
            return 0.0

        if settings is None:
            settings = {}

        webcam_enabled = settings.get("webcam_enabled", True)
        gaze_enabled = settings.get("gaze_enabled", True)
        tab_switch_enabled = settings.get("tab_switch_enabled", True)

        scores_by_type: Dict[ProctorEventType, float] = {}

        for ev in events:
            e_type = ev.get("event_type")
            if isinstance(e_type, str):
                try:
                    e_type = ProctorEventType(e_type)
                except ValueError:
                    continue

            # Skip disabled signals
            if not webcam_enabled and e_type in [ProctorEventType.NO_FACE, ProctorEventType.MULTIPLE_FACES, ProctorEventType.WEBCAM_SNAPSHOT]:
                continue
            if not gaze_enabled and e_type == ProctorEventType.GAZE_AWAY:
                continue
            if not tab_switch_enabled and e_type in [ProctorEventType.TAB_SWITCH, ProctorEventType.WINDOW_BLUR, ProctorEventType.FULLSCREEN_EXIT]:
                continue

            weight = SuspicionScorer.WEIGHTS.get(e_type, 5.0)
            scores_by_type[e_type] = scores_by_type.get(e_type, 0.0) + weight

        # Apply caps
        total_score = 0.0
        for e_type, raw_score in scores_by_type.items():
            cap = SuspicionScorer.CAPS.get(e_type, 100.0)
            total_score += min(raw_score, cap)

        # Clamp between 0.0 and 100.0
        return max(0.0, min(100.0, round(total_score, 2)))
