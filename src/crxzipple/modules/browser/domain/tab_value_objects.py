from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .exceptions import BrowserValidationError
from .value_helpers import (
    _normalize_confidence,
    _normalize_endpoint_map,
    _normalize_frame_path,
    _normalize_numeric_mapping,
    _normalize_optional_text,
    _normalize_ref_id,
    _normalize_text_tuple,
)
from .value_types import BrowserTabType


@dataclass(frozen=True, slots=True)
class BrowserTab:
    target_id: str
    url: str = ""
    title: str = ""
    type: BrowserTabType = "page"
    ws_url: str | None = None
    json_endpoints: dict[str, str] | None = None

    def __post_init__(self) -> None:
        normalized_target_id = self.target_id.strip()
        if not normalized_target_id:
            raise BrowserValidationError("target_id is required.")
        object.__setattr__(self, "target_id", normalized_target_id)
        object.__setattr__(self, "url", self.url.strip())
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "ws_url", _normalize_optional_text(self.ws_url))
        object.__setattr__(
            self,
            "json_endpoints",
            _normalize_endpoint_map(self.json_endpoints),
        )


@dataclass(frozen=True, slots=True)
class BrowserActionTarget:
    target_id: str | None = None
    ref: str | None = None
    selector: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _normalize_optional_text(self.target_id))
        object.__setattr__(
            self,
            "ref",
            (_normalize_ref_id(self.ref) if self.ref is not None else None),
        )
        object.__setattr__(self, "selector", _normalize_optional_text(self.selector))


@dataclass(frozen=True, slots=True)
class BrowserStoredRef:
    ref: str
    selector: str | None = None
    scope_selector: str | None = None
    uid: str | None = None
    nth: int | None = None
    generation: int = 1
    snapshot_format: str | None = None
    frame_path: tuple[int, ...] = ()
    label: str | None = None
    role: str | None = None
    text: str | None = None
    tag: str | None = None
    frame_id: str | None = None
    backend_node_id: int | None = None
    bbox: Mapping[str, Any] | None = None
    evidence: tuple[str, ...] = ()
    confidence: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", _normalize_ref_id(self.ref))
        selector = _normalize_optional_text(self.selector)
        scope_selector = _normalize_optional_text(self.scope_selector)
        uid = _normalize_optional_text(self.uid)
        role = _normalize_optional_text(self.role)
        if (
            selector is None
            and uid is None
            and role is None
            and self.backend_node_id is None
        ):
            raise BrowserValidationError(
                "stored refs require selector, uid, role, or backend_node_id.",
            )
        object.__setattr__(self, "selector", selector)
        object.__setattr__(self, "scope_selector", scope_selector)
        object.__setattr__(self, "uid", uid)
        if self.nth is None:
            object.__setattr__(self, "nth", None)
        else:
            nth = int(self.nth)
            if nth < 0:
                raise BrowserValidationError(
                    "stored ref nth must be greater than or equal to 0."
                )
            object.__setattr__(self, "nth", nth)
        generation = int(self.generation)
        if generation < 1:
            raise BrowserValidationError(
                "stored ref generation must be greater than or equal to 1."
            )
        object.__setattr__(self, "generation", generation)
        object.__setattr__(
            self,
            "snapshot_format",
            _normalize_optional_text(self.snapshot_format),
        )
        object.__setattr__(self, "frame_path", _normalize_frame_path(self.frame_path))
        object.__setattr__(self, "label", _normalize_optional_text(self.label))
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "text", _normalize_optional_text(self.text))
        object.__setattr__(self, "tag", _normalize_optional_text(self.tag))
        object.__setattr__(self, "frame_id", _normalize_optional_text(self.frame_id))
        if self.backend_node_id is None:
            object.__setattr__(self, "backend_node_id", None)
        else:
            backend_node_id = int(self.backend_node_id)
            if backend_node_id < 1:
                raise BrowserValidationError(
                    "stored ref backend_node_id must be greater than or equal to 1.",
                )
            object.__setattr__(self, "backend_node_id", backend_node_id)
        object.__setattr__(self, "bbox", _normalize_numeric_mapping(self.bbox))
        object.__setattr__(self, "evidence", _normalize_text_tuple(self.evidence))
        object.__setattr__(self, "confidence", _normalize_confidence(self.confidence))
