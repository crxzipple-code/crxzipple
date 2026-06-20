from __future__ import annotations

from enum import Enum


class RuntimeRequestMode(str, Enum):
    NORMAL_TURN = "normal_turn"
    APPROVAL_RESUME = "approval_resume"
    APPROVAL_DENIED = "approval_denied"
    SESSION_START = "session_start"
    RECOVERY_RESUME = "recovery_resume"
    HEARTBEAT = "heartbeat"
    MEMORY_FLUSH = "memory_flush"
    COMPACTION = "compaction"
