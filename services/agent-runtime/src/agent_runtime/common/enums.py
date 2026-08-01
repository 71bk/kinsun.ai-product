from enum import Enum


class SafetyDecision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    SAFE_FALLBACK = "SAFE_FALLBACK"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ResultStatus(str, Enum):
    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"
    SAFE_FALLBACK = "SAFE_FALLBACK"
    FAILED = "FAILED"


class ActorRole(str, Enum):
    ELDER = "elder"
    FAMILY = "family"
    STAFF = "staff"
    SYSTEM = "system"
