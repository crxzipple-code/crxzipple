from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ListSessionItemsInput:
    session_key: str
    limit: int | None = None
    active_session_only: bool = False
    after_sequence_no: int | None = None
    before_sequence_no: int | None = None


@dataclass(frozen=True, slots=True)
class BuildSessionReplayWindowInput:
    session_key: str
    limit: int | None = None
    active_session_only: bool = False
    after_sequence_no: int | None = None
    before_sequence_no: int | None = None


@dataclass(frozen=True, slots=True)
class BuildSessionMaintenanceWindowInput:
    session_key: str
    limit: int | None = None
    active_session_only: bool = False
    after_sequence_no: int | None = None
    before_sequence_no: int | None = None


@dataclass(frozen=True, slots=True)
class ListSessionItemRangeInput:
    session_key: str
    session_id: str
    from_sequence_no: int | None = None
    to_sequence_no: int | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ListSessionSegmentHandlesInput:
    session_key: str
    include_active: bool = True
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class GetSessionItemBySourceInput:
    session_key: str
    session_id: str
    source_module: str
    source_kind: str
    source_id: str


@dataclass(frozen=True, slots=True)
class GetSessionContextFrontierInput:
    session_key: str
    active_item_limit: int | None = None
    historical_instance_limit: int | None = None


@dataclass(frozen=True, slots=True)
class ListSessionInstancesInput:
    session_key: str
