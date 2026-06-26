from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.context_workspace.domain import ContextEstimate
from crxzipple.modules.context_workspace.domain.value_objects import JsonObject


@dataclass(frozen=True, slots=True)
class BuildContextObservationSliceInput:
    session_key: str
    run_id: str
    audience: str = "llm_request"
    provider_profile: str | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BuildContextControlSliceInput:
    session_key: str
    run_id: str
    audience: str = "llm_request"
    provider_profile: str | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextControlRef:
    node_id: str
    owner: str
    kind: str
    title: str = ""
    owner_ref: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "node_id": self.node_id,
            "owner": self.owner,
            "kind": self.kind,
            "title": self.title,
            "owner_ref": dict(self.owner_ref),
            "metadata": dict(self.metadata),
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextControlReport:
    selected_node_ids: tuple[str, ...] = ()
    omitted_node_ids: tuple[str, ...] = ()
    collapsed_refs: tuple[JsonObject, ...] = ()
    archived_refs: tuple[JsonObject, ...] = ()
    protocol_required_refs: tuple[JsonObject, ...] = ()
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "selected_node_ids": list(self.selected_node_ids),
            "omitted_node_ids": list(self.omitted_node_ids),
            "selected_count": len(self.selected_node_ids),
            "omitted_count": len(self.omitted_node_ids),
            "collapsed_refs": [dict(item) for item in self.collapsed_refs],
            "archived_refs": [dict(item) for item in self.archived_refs],
            "protocol_required_refs": [
                dict(item) for item in self.protocol_required_refs
            ],
            "metadata": dict(self.metadata),
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextSliceItem:
    item_id: str
    section: str
    owner: str
    kind: str
    title: str
    summary: str = ""
    text: str = ""
    content: object | None = None
    owner_ref: JsonObject = field(default_factory=dict)
    node_id: str | None = None
    estimate: ContextEstimate = field(default_factory=ContextEstimate)
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "item_id": self.item_id,
            "section": self.section,
            "owner": self.owner,
            "kind": self.kind,
            "title": self.title,
            "summary": self.summary,
            "text": self.text,
            "content": self.content,
            "owner_ref": dict(self.owner_ref),
            "estimate": self.estimate.to_payload(),
            "metadata": dict(self.metadata),
        }
        if self.node_id is not None:
            payload["node_id"] = self.node_id
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextSliceToolRef:
    tool_ref_id: str
    source_id: str
    function_name: str
    schema: JsonObject = field(default_factory=dict)
    owner_ref: JsonObject = field(default_factory=dict)
    node_id: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "tool_ref_id": self.tool_ref_id,
            "source_id": self.source_id,
            "function_name": self.function_name,
            "schema": dict(self.schema),
            "owner_ref": dict(self.owner_ref),
            "metadata": dict(self.metadata),
        }
        if self.node_id is not None:
            payload["node_id"] = self.node_id
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextControlSlice:
    slice_id: str
    session_key: str
    run_id: str
    audience: str
    tree_revision: int
    selected_refs: tuple[ContextControlRef, ...] = ()
    active_tools: tuple[ContextSliceToolRef, ...] = ()
    report: ContextControlReport = field(default_factory=ContextControlReport)
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "slice_id": self.slice_id,
            "session_key": self.session_key,
            "run_id": self.run_id,
            "audience": self.audience,
            "tree_revision": self.tree_revision,
            "selected_refs": [item.to_payload() for item in self.selected_refs],
            "active_tools": [tool.to_payload() for tool in self.active_tools],
            "report": self.report.to_payload(),
            "metadata": dict(self.metadata),
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextSliceReport:
    included_node_ids: tuple[str, ...] = ()
    omitted_node_ids: tuple[str, ...] = ()
    archived_refs: tuple[JsonObject, ...] = ()
    collapsed_refs: tuple[JsonObject, ...] = ()
    redacted_refs: tuple[JsonObject, ...] = ()
    unresolved_refs: tuple[JsonObject, ...] = ()
    budget: JsonObject = field(default_factory=dict)
    loss: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "included_node_ids": list(self.included_node_ids),
            "omitted_node_ids": list(self.omitted_node_ids),
            "included_count": len(self.included_node_ids),
            "omitted_count": len(self.omitted_node_ids),
            "archived_refs": [dict(item) for item in self.archived_refs],
            "collapsed_refs": [dict(item) for item in self.collapsed_refs],
            "redacted_refs": [dict(item) for item in self.redacted_refs],
            "unresolved_refs": [dict(item) for item in self.unresolved_refs],
            "budget": dict(self.budget),
            "loss": dict(self.loss),
            "metadata": dict(self.metadata),
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


@dataclass(frozen=True, slots=True)
class ContextSlice:
    slice_id: str
    session_key: str
    run_id: str
    audience: str
    tree_revision: int
    items: tuple[ContextSliceItem, ...] = ()
    active_tools: tuple[ContextSliceToolRef, ...] = ()
    report: ContextSliceReport = field(default_factory=ContextSliceReport)
    provider_attachments: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "slice_id": self.slice_id,
            "session_key": self.session_key,
            "run_id": self.run_id,
            "audience": self.audience,
            "tree_revision": self.tree_revision,
            "items": [item.to_payload() for item in self.items],
            "active_tools": [tool.to_payload() for tool in self.active_tools],
            "report": self.report.to_payload(),
            "provider_attachments": dict(self.provider_attachments),
            "metadata": dict(self.metadata),
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


__all__ = [
    "BuildContextControlSliceInput",
    "BuildContextObservationSliceInput",
    "ContextControlRef",
    "ContextControlReport",
    "ContextControlSlice",
    "ContextSlice",
    "ContextSliceItem",
    "ContextSliceReport",
    "ContextSliceToolRef",
]
