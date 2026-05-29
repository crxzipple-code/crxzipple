from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.memory.domain.value_objects import (
    ChunkRange,
    MemoryFileKind,
    MemoryPolicyStatus,
    MemoryPolicyTargetKind,
    MemorySpaceOwnerKind,
    MemorySpaceStatus,
)
from crxzipple.shared.time import coerce_utc_datetime


@dataclass(frozen=True, slots=True)
class IndexedMemoryFile:
    path: str
    kind: MemoryFileKind
    source_file_hash: str
    mtime_ns: int
    size_bytes: int
    text: str


@dataclass(frozen=True, slots=True)
class MemoryItem:
    id: str
    space_id: str
    path: str
    kind: MemoryFileKind
    chunk_range: ChunkRange
    preview: str
    content_hash: str
    source_file_hash: str
    updated_at: int

    @property
    def start_line(self) -> int:
        return self.chunk_range.start_line

    @property
    def end_line(self) -> int:
        return self.chunk_range.end_line


@dataclass(frozen=True, slots=True)
class MemorySpace:
    scope_ref: str
    owner_kind: MemorySpaceOwnerKind
    owner_id: str
    engine_id: str
    storage_root: str
    retrieval_backend: str
    status: MemorySpaceStatus = "active"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        values = {
            "scope_ref": self.scope_ref,
            "owner_kind": self.owner_kind,
            "owner_id": self.owner_id,
            "engine_id": self.engine_id,
            "storage_root": self.storage_root,
            "retrieval_backend": self.retrieval_backend,
            "status": self.status,
        }
        for field_name, value in values.items():
            normalized = _normalize_required_text(str(value), field_name)
            object.__setattr__(self, field_name, normalized)
        if self.status not in {"active", "disabled"}:
            raise ValueError(f"Unsupported memory space status '{self.status}'.")
        if self.owner_kind not in {"agent", "shared", "project", "team", "system"}:
            raise ValueError(f"Unsupported memory space owner kind '{self.owner_kind}'.")
        object.__setattr__(self, "metadata", dict(self.metadata))
        object.__setattr__(self, "created_at", coerce_utc_datetime(self.created_at))
        object.__setattr__(self, "updated_at", coerce_utc_datetime(self.updated_at))

    @property
    def enabled(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    policy_id: str
    target_kind: MemoryPolicyTargetKind
    target_id: str | None = None
    recall_enabled: bool = True
    remember_enabled: bool = True
    max_recall_items: int = 6
    retention: str = "engine_default"
    status: MemoryPolicyStatus = "active"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_id",
            _normalize_required_text(self.policy_id, "policy_id"),
        )
        object.__setattr__(
            self,
            "target_kind",
            _normalize_required_text(self.target_kind, "target_kind"),
        )
        if self.target_kind not in {"global", "space", "agent"}:
            raise ValueError(f"Unsupported memory policy target kind '{self.target_kind}'.")
        normalized_target_id = (
            str(self.target_id).strip()
            if self.target_id is not None
            else None
        )
        if self.target_kind == "global":
            normalized_target_id = None
        elif not normalized_target_id:
            raise ValueError("MemoryPolicy.target_id is required for non-global policies.")
        object.__setattr__(self, "target_id", normalized_target_id)
        object.__setattr__(self, "max_recall_items", max(1, int(self.max_recall_items)))
        object.__setattr__(self, "retention", self.retention.strip() or "engine_default")
        if self.retention not in {"engine_default", "durable", "session", "temporary"}:
            raise ValueError(f"Unsupported memory policy retention '{self.retention}'.")
        if self.status not in {"active", "disabled"}:
            raise ValueError(f"Unsupported memory policy status '{self.status}'.")
        object.__setattr__(self, "metadata", dict(self.metadata))
        object.__setattr__(self, "created_at", coerce_utc_datetime(self.created_at))
        object.__setattr__(self, "updated_at", coerce_utc_datetime(self.updated_at))

    @property
    def enabled(self) -> bool:
        return self.status == "active"


def _normalize_required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"MemorySpace.{field_name} cannot be empty.")
    return normalized
