from enum import StrEnum


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class ComponentState(StrEnum):
    """Honest component states reported by health endpoints and the worker."""

    OK = "OK"
    DEGRADED = "DEGRADED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNKNOWN = "UNKNOWN"


class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class CameraStatus(StrEnum):
    DISABLED = "DISABLED"
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    PAUSED = "PAUSED"


class DesiredState(StrEnum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"


class SourceKind(StrEnum):
    RTSP = "RTSP"
    VIDEO_FILE = "VIDEO_FILE"
    TEST_FAKE = "TEST_FAKE"  # visibly labeled test/demo only


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class IncidentOutcome(StrEnum):
    TRUE_SMOKE = "TRUE_SMOKE"
    FALSE_ALARM = "FALSE_ALARM"
    UNKNOWN = "UNKNOWN"


class Decision(StrEnum):
    NONE = "NONE"
    CANDIDATE = "CANDIDATE"
    VERIFIED_BY_RULES = "VERIFIED_BY_RULES"
    UNCERTAIN = "UNCERTAIN"


class EvidenceType(StrEnum):
    ORIGINAL = "original"
    ANNOTATED = "annotated"
    CROP = "crop"


class EmailDeliveryState(StrEnum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    ACCEPTED_BY_SMTP = "ACCEPTED_BY_SMTP"
    RETRY = "RETRY"
    FAILED = "FAILED"


class NotificationCategory(StrEnum):
    INCIDENT = "incident"
    TEST = "test"
    CAMERA_OFFLINE = "camera_offline"
    SERVICE_DEGRADED = "service_degraded"


class CommandStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
