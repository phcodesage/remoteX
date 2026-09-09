from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum


class SessionStatus(StrEnum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    ACTIVE = "active"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ENDED = "ended"


class SignalType(StrEnum):
    OFFER = "offer"
    ANSWER = "answer"
    ICE_CANDIDATE = "ice_candidate"
    SESSION_READY = "session_ready"
    SESSION_APPROVED = "session_approved"
    SESSION_REJECTED = "session_rejected"
    SESSION_REVOKED = "session_revoked"
    SESSION_ENDED = "session_ended"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


def iso(value: datetime | None) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
