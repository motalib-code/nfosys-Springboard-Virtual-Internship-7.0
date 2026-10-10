import enum


class UserRole(str, enum.Enum):
    STUDENT = "student"
    EXAMINER = "examiner"
    ADMIN = "admin"


class QuestionType(str, enum.Enum):
    MCQ = "MCQ"
    MULTI_SELECT = "multi_select"
    SHORT_ANSWER = "short_answer"
    LONG_ANSWER = "long_answer"
    IMAGE_UPLOAD = "image_upload"


class Difficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class RandomizationMode(str, enum.Enum):
    NONE = "none"
    PER_STUDENT_UNIQUE = "per_student_unique"


class ExamStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class SessionStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    AUTO_SUBMITTED = "auto_submitted"
    FLAGGED = "flagged"
    TERMINATED = "terminated"


class ProctorEventType(str, enum.Enum):
    WEBCAM_SNAPSHOT = "webcam_snapshot"
    GAZE_AWAY = "gaze_away"
    TAB_SWITCH = "tab_switch"
    MULTIPLE_FACES = "multiple_faces"
    NO_FACE = "no_face"
    WINDOW_BLUR = "window_blur"
    FULLSCREEN_EXIT = "fullscreen_exit"
    HEARTBEAT_LOST = "heartbeat_lost"
    CONCURRENT_SESSION = "concurrent_session"
    IP_CHANGE = "ip_change"
    SCORE_UPDATE = "score_update"


class SubmittedReason(str, enum.Enum):
    MANUAL = "manual"
    TIME_EXPIRED = "time_expired"
    PROCTOR_TERMINATED = "proctor_terminated"
    ADMIN_FORCED = "admin_forced"


class GradingStatus(str, enum.Enum):
    PENDING = "pending"
    AUTO_GRADED = "auto_graded"
    MANUALLY_GRADED = "manually_graded"
    FINAL = "final"
