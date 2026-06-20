from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from crxzipple.modules.context_workspace.domain.exceptions import (
    ContextWorkspaceValidationError,
)
from crxzipple.shared.time import coerce_utc_datetime


JsonObject = dict[str, Any]


class ContextAction(StrEnum):
    EXPAND = "expand"
    COLLAPSE = "collapse"
    PIN = "pin"
    UNPIN = "unpin"
    UPSERT = "upsert"
    ENABLE_TOOL_SCHEMA = "enable_tool_schema"
    DISABLE_TOOL_SCHEMA = "disable_tool_schema"
    ESTIMATE = "estimate"


class ContextActorKind(StrEnum):
    AGENT = "agent"
    USER = "user"
    RUNTIME = "runtime"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class ContextActor:
    kind: ContextActorKind = ContextActorKind.SYSTEM
    actor_id: str | None = None

    def __post_init__(self) -> None:
        if self.actor_id is not None and not self.actor_id.strip():
            raise ContextWorkspaceValidationError("actor_id cannot be blank.")

    def to_payload(self) -> JsonObject:
        return {"kind": self.kind.value, "actor_id": self.actor_id}


@dataclass(frozen=True, slots=True)
class ContextEstimate:
    text_chars: int = 0
    text_tokens: int = 0
    tool_schema_tokens: int = 0
    image_count: int = 0
    file_count: int = 0
    file_tokens: int = 0
    provider_attachment_count: int = 0

    def __post_init__(self) -> None:
        for field_name, value in self.to_payload().items():
            if int(value) < 0:
                raise ContextWorkspaceValidationError(
                    f"{field_name} cannot be negative.",
                )

    def plus(self, other: "ContextEstimate") -> "ContextEstimate":
        return ContextEstimate(
            text_chars=self.text_chars + other.text_chars,
            text_tokens=self.text_tokens + other.text_tokens,
            tool_schema_tokens=self.tool_schema_tokens + other.tool_schema_tokens,
            image_count=self.image_count + other.image_count,
            file_count=self.file_count + other.file_count,
            file_tokens=self.file_tokens + other.file_tokens,
            provider_attachment_count=(
                self.provider_attachment_count + other.provider_attachment_count
            ),
        )

    def to_payload(self) -> JsonObject:
        return {
            "text_chars": self.text_chars,
            "text_tokens": self.text_tokens,
            "tool_schema_tokens": self.tool_schema_tokens,
            "image_count": self.image_count,
            "file_count": self.file_count,
            "file_tokens": self.file_tokens,
            "provider_attachment_count": self.provider_attachment_count,
        }

    @classmethod
    def from_payload(cls, payload: JsonObject | None) -> "ContextEstimate":
        data = dict(payload or {})
        return cls(
            text_chars=int(data.get("text_chars") or 0),
            text_tokens=int(data.get("text_tokens") or 0),
            tool_schema_tokens=int(data.get("tool_schema_tokens") or 0),
            image_count=int(data.get("image_count") or 0),
            file_count=int(data.get("file_count") or 0),
            file_tokens=int(data.get("file_tokens") or 0),
            provider_attachment_count=int(data.get("provider_attachment_count") or 0),
        )


@dataclass(frozen=True, slots=True)
class ContextNodeState:
    collapsed: bool = True
    loaded: bool = False
    pinned: bool = False
    snapshot_visible: bool = True
    schema_enabled: bool = False
    opened: bool = False
    consumed: bool = False
    archived: bool = False
    summary_mode: str = "auto"
    included_in_next_slice: bool = False
    included_in_next_tool_surface: bool = False
    status: str = "available"
    render_priority: int = 0
    render_reason: str = ""

    def expand(self) -> "ContextNodeState":
        return self.with_updates(collapsed=False, loaded=True)

    def collapse(self) -> "ContextNodeState":
        return self.with_updates(collapsed=True)

    def with_updates(
        self,
        *,
        collapsed: bool | None = None,
        loaded: bool | None = None,
        pinned: bool | None = None,
        snapshot_visible: bool | None = None,
        schema_enabled: bool | None = None,
        opened: bool | None = None,
        consumed: bool | None = None,
        archived: bool | None = None,
        summary_mode: str | None = None,
        included_in_next_slice: bool | None = None,
        included_in_next_tool_surface: bool | None = None,
        status: str | None = None,
        render_priority: int | None = None,
        render_reason: str | None = None,
    ) -> "ContextNodeState":
        return ContextNodeState(
            collapsed=self.collapsed if collapsed is None else collapsed,
            loaded=self.loaded if loaded is None else loaded,
            pinned=self.pinned if pinned is None else pinned,
            snapshot_visible=(
                self.snapshot_visible if snapshot_visible is None else snapshot_visible
            ),
            schema_enabled=(
                self.schema_enabled if schema_enabled is None else schema_enabled
            ),
            opened=self.opened if opened is None else opened,
            consumed=self.consumed if consumed is None else consumed,
            archived=self.archived if archived is None else archived,
            summary_mode=self.summary_mode if summary_mode is None else summary_mode,
            included_in_next_slice=(
                self.included_in_next_slice
                if included_in_next_slice is None
                else included_in_next_slice
            ),
            included_in_next_tool_surface=(
                self.included_in_next_tool_surface
                if included_in_next_tool_surface is None
                else included_in_next_tool_surface
            ),
            status=self.status if status is None else status,
            render_priority=(
                self.render_priority if render_priority is None else render_priority
            ),
            render_reason=self.render_reason if render_reason is None else render_reason,
        )

    def to_payload(self) -> JsonObject:
        return {
            "collapsed": self.collapsed,
            "loaded": self.loaded,
            "pinned": self.pinned,
            "snapshot_visible": self.snapshot_visible,
            "schema_enabled": self.schema_enabled,
            "opened": self.opened,
            "consumed": self.consumed,
            "archived": self.archived,
            "summary_mode": self.summary_mode,
            "included_in_next_slice": self.included_in_next_slice,
            "included_in_next_tool_surface": self.included_in_next_tool_surface,
            "status": self.status,
            "render_priority": self.render_priority,
            "render_reason": self.render_reason,
        }

    @classmethod
    def from_payload(cls, payload: JsonObject | None) -> "ContextNodeState":
        data = dict(payload or {})
        return cls(
            collapsed=bool(data.get("collapsed", True)),
            loaded=bool(data.get("loaded", False)),
            pinned=bool(data.get("pinned", False)),
            snapshot_visible=bool(data.get("snapshot_visible", True)),
            schema_enabled=bool(data.get("schema_enabled", False)),
            opened=bool(data.get("opened", False)),
            consumed=bool(data.get("consumed", False)),
            archived=bool(data.get("archived", False)),
            summary_mode=str(data.get("summary_mode") or "auto"),
            included_in_next_slice=bool(data.get("included_in_next_slice", False)),
            included_in_next_tool_surface=bool(
                data.get("included_in_next_tool_surface", False),
            ),
            status=str(data.get("status") or "available"),
            render_priority=int(data.get("render_priority") or 0),
            render_reason=str(data.get("render_reason") or ""),
        )


@dataclass(frozen=True, slots=True)
class ContextNodeSeed:
    node_id: str
    owner: str
    kind: str
    title: str
    summary: str = ""
    content: str = ""
    parent_id: str | None = None
    state: ContextNodeState = field(default_factory=ContextNodeState)
    actions: tuple[ContextAction, ...] = ()
    owner_ref: JsonObject = field(default_factory=dict)
    estimate: ContextEstimate = field(default_factory=ContextEstimate)
    revision: str | None = None
    freshness: str = "live"
    display_order: int = 0
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.node_id, "node_id")
        _require_text(self.owner, "owner")
        _require_text(self.kind, "kind")
        _require_text(self.title, "title")
        if self.parent_id is not None:
            _require_text(self.parent_id, "parent_id")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_timestamp(value: datetime | None) -> datetime:
    return coerce_utc_datetime(value or utcnow())


def _require_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ContextWorkspaceValidationError(f"{label} cannot be blank.")
    return normalized


__all__ = [
    "ContextAction",
    "ContextActor",
    "ContextActorKind",
    "ContextEstimate",
    "ContextNodeSeed",
    "ContextNodeState",
    "JsonObject",
    "normalize_timestamp",
    "utcnow",
]
