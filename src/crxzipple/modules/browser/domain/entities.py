from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, TypeAlias

from .exceptions import BrowserValidationError
from .value_objects import BrowserStoredRef
from .value_objects import _normalize_optional_text, _normalize_profile_name

_PAGE_STATE_METADATA_KEY = "page_state_by_target"
_HOST_GENERATION_METADATA_KEY = "host_generation"
_PAGE_GENERATION_KEY = "page_generation"
_PAGE_GENERATION_REASON_KEY = "page_generation_reason"
_SNAPSHOT_GENERATION_KEY = "snapshot_generation"
_ACTIVE_OVERLAY_SELECTOR_KEY = "active_overlay_selector"
_ACTIVE_OVERLAY_KIND_KEY = "active_overlay_kind"
_ACTIVE_OVERLAY_SOURCE_REF_KEY = "active_overlay_source_ref"
_ACTIVE_OVERLAY_SOURCE_SELECTOR_KEY = "active_overlay_source_selector"
_ACTIVE_OVERLAY_SOURCE_SCOPE_SELECTOR_KEY = "active_overlay_source_scope_selector"
_OVERLAY_BINDINGS_BY_REF_KEY = "overlay_bindings_by_ref"
_OVERLAY_BINDINGS_BY_SELECTOR_KEY = "overlay_bindings_by_selector"
_OVERLAY_BINDINGS_BY_SCOPE_SELECTOR_KEY = "overlay_bindings_by_scope_selector"

BrowserAttachmentStatus: TypeAlias = Literal[
    "idle",
    "attaching",
    "attached",
    "degraded",
    "recovering",
    "closed",
    "failed",
]
BrowserProfileAllocationStatus: TypeAlias = Literal[
    "active",
    "released",
    "expired",
    "failed",
    "lost",
]
BrowserProfileAllocationConsumerKind: TypeAlias = Literal[
    "tool_run",
    "orchestration_run",
    "session",
    "agent",
    "manual",
]


def _normalize_browser_ref(value: object) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    if normalized.startswith("mcp:"):
        return None
    return normalized


def _normalize_allocation_id(value: object) -> str:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        raise BrowserValidationError("allocation id is required.")
    return normalized


def _normalize_pool_id(value: object) -> str:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        raise BrowserValidationError("pool id is required.")
    return normalized.lower()


def _normalize_consumer_id(value: object) -> str:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        raise BrowserValidationError("consumer id is required.")
    return normalized


def _normalize_consumer_kind(value: object) -> str:
    normalized = (_normalize_optional_text(value) or "").lower()
    if normalized not in {
        "tool_run",
        "orchestration_run",
        "session",
        "agent",
        "manual",
    }:
        raise BrowserValidationError(
            "consumer_kind must be one of: agent, manual, orchestration_run, session, tool_run.",
        )
    return normalized


def _normalize_allocation_status(value: object) -> str:
    normalized = (_normalize_optional_text(value) or "").lower()
    if normalized not in {"active", "released", "expired", "failed", "lost"}:
        raise BrowserValidationError(
            "allocation status must be one of: active, expired, failed, lost, released.",
        )
    return normalized


def _ensure_aware_utc(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    normalized = value.astimezone(timezone.utc)
    if normalized.year < 2000:
        raise BrowserValidationError(f"{label} is invalid.")
    return normalized


def _normalize_target_host(value: object) -> str | None:
    normalized = _normalize_optional_text(value)
    return normalized.lower() if normalized is not None else None


def _normalize_target_ids(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        candidates: object = (value,)
    else:
        candidates = value
    if not isinstance(candidates, (list, tuple, set)):
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        target_id = _normalize_optional_text(str(item) if item is not None else None)
        if target_id is None or target_id in seen:
            continue
        seen.add(target_id)
        normalized.append(target_id)
    return tuple(normalized)


@dataclass(slots=True)
class BrowserProfileRuntimeState:
    profile_name: str
    attachment_status: BrowserAttachmentStatus = "idle"
    browser_ref: str | None = None
    last_target_id: str | None = None
    running_pid: int | None = None
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.profile_name = _normalize_profile_name(self.profile_name)
        self.browser_ref = _normalize_browser_ref(self.browser_ref)
        self.last_target_id = _normalize_optional_text(self.last_target_id)
        self.last_error = _normalize_optional_text(self.last_error)
        if self.attachment_status not in {
            "idle",
            "attaching",
            "attached",
            "degraded",
            "recovering",
            "closed",
            "failed",
        }:
            raise BrowserValidationError(
                f"Unsupported attachment status '{self.attachment_status}'.",
            )
        if self.running_pid is not None and int(self.running_pid) < 1:
            raise BrowserValidationError(
                "running_pid must be greater than or equal to 1.",
            )

    def mark_attaching(self) -> None:
        self.attachment_status = "attaching"
        self.last_error = None

    def mark_attached(
        self,
        *,
        browser_ref: str | None = None,
        running_pid: int | None = None,
    ) -> None:
        self.attachment_status = "attached"
        self.browser_ref = _normalize_browser_ref(browser_ref) or self.browser_ref
        self.running_pid = running_pid if running_pid is not None else self.running_pid
        self.last_error = None

    def mark_degraded(self, reason: str | None = None) -> None:
        self.attachment_status = "degraded"
        self.last_error = _normalize_optional_text(reason)

    def mark_recovering(self) -> None:
        self.attachment_status = "recovering"

    def mark_failed(self, reason: str) -> None:
        self.attachment_status = "failed"
        self.browser_ref = None
        self.running_pid = None
        self.last_target_id = None
        self.last_error = _normalize_optional_text(reason)

    def mark_closed(self) -> None:
        self.attachment_status = "closed"
        self.browser_ref = None
        self.running_pid = None

    def host_generation(self) -> str | None:
        return _normalize_optional_text(self.metadata.get(_HOST_GENERATION_METADATA_KEY))

    def remember_host_generation(self, generation: str | None) -> bool:
        normalized = _normalize_optional_text(generation)
        previous = self.host_generation()
        if normalized is None:
            self.metadata.pop(_HOST_GENERATION_METADATA_KEY, None)
        else:
            self.metadata[_HOST_GENERATION_METADATA_KEY] = normalized
        return previous is not None and normalized is not None and previous != normalized

    def remember_target(self, target_id: str | None) -> None:
        self.last_target_id = _normalize_optional_text(target_id)

    def remember_page_action(
        self,
        *,
        target_id: str,
        action_kind: str,
    ) -> None:
        normalized_target = _normalize_optional_text(target_id)
        normalized_kind = _normalize_optional_text(action_kind)
        if normalized_target is None or normalized_kind is None:
            return
        state = self._page_state(normalized_target)
        state.setdefault(_PAGE_GENERATION_KEY, 1)
        state["last_action_kind"] = normalized_kind

    def remember_page_opened(self, *, target_id: str) -> None:
        normalized_target = _normalize_optional_text(target_id)
        if normalized_target is None:
            return
        state = self._page_state(normalized_target)
        state.setdefault(_PAGE_GENERATION_KEY, 1)
        state[_PAGE_GENERATION_REASON_KEY] = "open-tab"

    def reset_page_state(
        self,
        *,
        target_id: str,
        reason: str,
    ) -> None:
        normalized_target = _normalize_optional_text(target_id)
        normalized_reason = _normalize_optional_text(reason) or "changed"
        if normalized_target is None:
            return
        previous_generation = self.page_generation(target_id=normalized_target)
        page_states = self.metadata.get(_PAGE_STATE_METADATA_KEY)
        if not isinstance(page_states, dict):
            page_states = {}
            self.metadata[_PAGE_STATE_METADATA_KEY] = page_states
        page_states[normalized_target] = {
            _PAGE_GENERATION_KEY: previous_generation + 1,
            _PAGE_GENERATION_REASON_KEY: normalized_reason,
        }

    def page_generation(self, *, target_id: str) -> int:
        state = self.page_state(target_id=target_id) or {}
        try:
            numeric = int(state.get(_PAGE_GENERATION_KEY) or 0)
        except (TypeError, ValueError):
            return 0
        return max(numeric, 0)

    def remember_page_snapshot(
        self,
        *,
        target_id: str,
        generation: int,
        snapshot_format: str,
        ref_count: int,
        frame_count: int,
    ) -> None:
        normalized_target = _normalize_optional_text(target_id)
        normalized_format = _normalize_optional_text(snapshot_format)
        if normalized_target is None or normalized_format is None:
            return
        state = self._page_state(normalized_target)
        state.setdefault(_PAGE_GENERATION_KEY, 1)
        state["last_action_kind"] = "snapshot"
        state["current_ref_generation"] = max(int(generation), 1)
        state[_SNAPSHOT_GENERATION_KEY] = max(int(generation), 1)
        state["last_snapshot_format"] = normalized_format
        state["last_snapshot_ref_count"] = max(int(ref_count), 0)
        state["last_snapshot_frame_count"] = max(int(frame_count), 0)
        state["ref_session_restored"] = False

    def restore_page_ref_session(
        self,
        *,
        target_id: str,
        refs: tuple[BrowserStoredRef, ...],
    ) -> bool:
        normalized_target = _normalize_optional_text(target_id)
        if normalized_target is None or not refs:
            return False
        state = self._page_state(normalized_target)
        current_generation = state.get("current_ref_generation")
        if current_generation not in {None, ""}:
            return False

        latest_generation = max(max(int(ref.generation), 1) for ref in refs)
        active_refs = tuple(ref for ref in refs if max(int(ref.generation), 1) == latest_generation)
        snapshot_format = next(
            (
                normalized
                for normalized in (
                    _normalize_optional_text(ref.snapshot_format)
                    for ref in active_refs
                )
                if normalized is not None
            ),
            "snapshot",
        )
        state["last_action_kind"] = "snapshot"
        state.setdefault(_PAGE_GENERATION_KEY, 1)
        state["current_ref_generation"] = latest_generation
        state[_SNAPSHOT_GENERATION_KEY] = latest_generation
        state["last_snapshot_format"] = snapshot_format
        state["last_snapshot_ref_count"] = len(active_refs)
        state["last_snapshot_frame_count"] = len({ref.frame_path for ref in active_refs})
        state["ref_session_restored"] = True
        return True

    def next_ref_generation(self, *, target_id: str) -> int:
        normalized_target = _normalize_optional_text(target_id)
        if normalized_target is None:
            return 1
        state = self._page_state(normalized_target)
        current = state.get("current_ref_generation")
        try:
            numeric = int(current)
        except (TypeError, ValueError):
            numeric = 0
        return max(numeric + 1, 1)

    def remember_active_overlay(
        self,
        *,
        target_id: str,
        overlay_selector: str,
        overlay_kind: str | None = None,
        source_ref: str | None = None,
        source_selector: str | None = None,
        source_scope_selector: str | None = None,
    ) -> None:
        normalized_target = _normalize_optional_text(target_id)
        normalized_overlay = _normalize_optional_text(overlay_selector)
        if normalized_target is None or normalized_overlay is None:
            return
        state = self._page_state(normalized_target)
        state[_ACTIVE_OVERLAY_SELECTOR_KEY] = normalized_overlay
        normalized_overlay_kind = _normalize_optional_text(overlay_kind)
        state[_ACTIVE_OVERLAY_KIND_KEY] = normalized_overlay_kind
        normalized_source_ref = _normalize_optional_text(source_ref)
        normalized_source_selector = _normalize_optional_text(
            source_selector,
        )
        normalized_source_scope_selector = _normalize_optional_text(
            source_scope_selector,
        )
        state[_ACTIVE_OVERLAY_SOURCE_REF_KEY] = normalized_source_ref
        state[_ACTIVE_OVERLAY_SOURCE_SELECTOR_KEY] = normalized_source_selector
        state[_ACTIVE_OVERLAY_SOURCE_SCOPE_SELECTOR_KEY] = normalized_source_scope_selector
        if normalized_source_ref is not None:
            bindings = state.get(_OVERLAY_BINDINGS_BY_REF_KEY)
            if not isinstance(bindings, dict):
                bindings = {}
                state[_OVERLAY_BINDINGS_BY_REF_KEY] = bindings
            bindings[normalized_source_ref] = normalized_overlay
        if normalized_source_selector is not None:
            bindings = state.get(_OVERLAY_BINDINGS_BY_SELECTOR_KEY)
            if not isinstance(bindings, dict):
                bindings = {}
                state[_OVERLAY_BINDINGS_BY_SELECTOR_KEY] = bindings
            bindings[normalized_source_selector] = normalized_overlay
        if normalized_source_scope_selector is not None:
            bindings = state.get(_OVERLAY_BINDINGS_BY_SCOPE_SELECTOR_KEY)
            if not isinstance(bindings, dict):
                bindings = {}
                state[_OVERLAY_BINDINGS_BY_SCOPE_SELECTOR_KEY] = bindings
            bindings[normalized_source_scope_selector] = normalized_overlay

    def clear_active_overlay(self, *, target_id: str) -> None:
        normalized_target = _normalize_optional_text(target_id)
        if normalized_target is None:
            return
        page_states = self.metadata.get(_PAGE_STATE_METADATA_KEY)
        if not isinstance(page_states, dict):
            return
        state = page_states.get(normalized_target)
        if not isinstance(state, dict):
            return
        state.pop(_ACTIVE_OVERLAY_SELECTOR_KEY, None)
        state.pop(_ACTIVE_OVERLAY_KIND_KEY, None)
        state.pop(_ACTIVE_OVERLAY_SOURCE_REF_KEY, None)
        state.pop(_ACTIVE_OVERLAY_SOURCE_SELECTOR_KEY, None)
        state.pop(_ACTIVE_OVERLAY_SOURCE_SCOPE_SELECTOR_KEY, None)

    def active_overlay_context(self, *, target_id: str) -> dict[str, Any] | None:
        state = self.page_state(target_id=target_id)
        if not isinstance(state, dict):
            return None
        selector = _normalize_optional_text(state.get(_ACTIVE_OVERLAY_SELECTOR_KEY))
        if selector is None:
            return None
        return {
            "selector": selector,
            "kind": _normalize_optional_text(state.get(_ACTIVE_OVERLAY_KIND_KEY)),
            "source_ref": _normalize_optional_text(
                state.get(_ACTIVE_OVERLAY_SOURCE_REF_KEY),
            ),
            "source_selector": _normalize_optional_text(
                state.get(_ACTIVE_OVERLAY_SOURCE_SELECTOR_KEY),
            ),
            "source_scope_selector": _normalize_optional_text(
                state.get(_ACTIVE_OVERLAY_SOURCE_SCOPE_SELECTOR_KEY),
            ),
        }

    def active_overlay_selector(
        self,
        *,
        target_id: str,
        overlay_kind: str | None = None,
        source_refs: tuple[str, ...] = (),
        source_selectors: tuple[str, ...] = (),
        source_scope_selectors: tuple[str, ...] = (),
    ) -> str | None:
        state = self.page_state(target_id=target_id)
        if not isinstance(state, dict):
            return None

        normalized_refs = tuple(
            normalized
            for normalized in (
                _normalize_optional_text(item)
                for item in source_refs
            )
            if normalized is not None
        )
        normalized_selectors = tuple(
            normalized
            for normalized in (
                _normalize_optional_text(item)
                for item in source_selectors
            )
            if normalized is not None
        )
        normalized_scope_selectors = tuple(
            normalized
            for normalized in (
                _normalize_optional_text(item)
                for item in source_scope_selectors
            )
            if normalized is not None
        )

        if normalized_refs or normalized_selectors or normalized_scope_selectors:
            bindings_by_ref = state.get(_OVERLAY_BINDINGS_BY_REF_KEY)
            if isinstance(bindings_by_ref, dict):
                for candidate in normalized_refs:
                    resolved = _normalize_optional_text(bindings_by_ref.get(candidate))
                    if resolved is not None:
                        return resolved
            bindings_by_selector = state.get(_OVERLAY_BINDINGS_BY_SELECTOR_KEY)
            if isinstance(bindings_by_selector, dict):
                for candidate in normalized_selectors:
                    resolved = _normalize_optional_text(bindings_by_selector.get(candidate))
                    if resolved is not None:
                        return resolved
            bindings_by_scope_selector = state.get(_OVERLAY_BINDINGS_BY_SCOPE_SELECTOR_KEY)
            if isinstance(bindings_by_scope_selector, dict):
                for candidate in normalized_scope_selectors:
                    resolved = _normalize_optional_text(bindings_by_scope_selector.get(candidate))
                    if resolved is not None:
                        return resolved

        selector = _normalize_optional_text(state.get(_ACTIVE_OVERLAY_SELECTOR_KEY))
        if selector is None:
            return None
        stored_kind = _normalize_optional_text(state.get(_ACTIVE_OVERLAY_KIND_KEY))
        normalized_overlay_kind = _normalize_optional_text(overlay_kind)
        if normalized_overlay_kind is not None and stored_kind is not None and stored_kind != normalized_overlay_kind:
            return None

        stored_ref = _normalize_optional_text(state.get(_ACTIVE_OVERLAY_SOURCE_REF_KEY))
        stored_selector = _normalize_optional_text(state.get(_ACTIVE_OVERLAY_SOURCE_SELECTOR_KEY))
        stored_scope_selector = _normalize_optional_text(
            state.get(_ACTIVE_OVERLAY_SOURCE_SCOPE_SELECTOR_KEY),
        )
        if (normalized_refs or normalized_selectors or normalized_scope_selectors) and (
            stored_ref is not None or stored_selector is not None or stored_scope_selector is not None
        ):
            if stored_ref is not None and stored_ref in normalized_refs:
                return selector
            if stored_selector is not None and stored_selector in normalized_selectors:
                return selector
            if (
                stored_scope_selector is not None
                and stored_scope_selector in normalized_scope_selectors
            ):
                return selector
            return None
        return selector

    def forget_page(self, *, target_id: str) -> None:
        normalized_target = _normalize_optional_text(target_id)
        if normalized_target is None:
            return
        page_states = self.metadata.get(_PAGE_STATE_METADATA_KEY)
        if not isinstance(page_states, dict):
            return
        page_states.pop(normalized_target, None)
        if not page_states:
            self.metadata.pop(_PAGE_STATE_METADATA_KEY, None)

    def forget_all_pages(self) -> None:
        self.metadata.pop(_PAGE_STATE_METADATA_KEY, None)

    def page_state(self, *, target_id: str) -> dict[str, Any] | None:
        normalized_target = _normalize_optional_text(target_id)
        if normalized_target is None:
            return None
        page_states = self.metadata.get(_PAGE_STATE_METADATA_KEY)
        if not isinstance(page_states, dict):
            return None
        state = page_states.get(normalized_target)
        return dict(state) if isinstance(state, dict) else None

    def _page_state(self, target_id: str) -> dict[str, Any]:
        page_states = self.metadata.get(_PAGE_STATE_METADATA_KEY)
        if not isinstance(page_states, dict):
            page_states = {}
            self.metadata[_PAGE_STATE_METADATA_KEY] = page_states
        state = page_states.get(target_id)
        if not isinstance(state, dict):
            state = {}
            page_states[target_id] = state
        return state


@dataclass(frozen=True, slots=True)
class BrowserProfileAllocation:
    allocation_id: str
    pool_id: str
    profile_name: str
    consumer_kind: BrowserProfileAllocationConsumerKind
    consumer_id: str
    target_host: str | None = None
    status: BrowserProfileAllocationStatus = "active"
    acquired_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(seconds=900),
    )
    last_heartbeat_at: datetime | None = None
    released_at: datetime | None = None
    release_reason: str | None = None
    owned_target_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        acquired_at = _ensure_aware_utc(self.acquired_at, label="acquired_at")
        expires_at = _ensure_aware_utc(self.expires_at, label="expires_at")
        if expires_at <= acquired_at:
            raise BrowserValidationError("expires_at must be after acquired_at.")
        released_at = (
            _ensure_aware_utc(self.released_at, label="released_at")
            if self.released_at is not None
            else None
        )
        last_heartbeat_at = (
            _ensure_aware_utc(self.last_heartbeat_at, label="last_heartbeat_at")
            if self.last_heartbeat_at is not None
            else None
        )
        object.__setattr__(
            self,
            "allocation_id",
            _normalize_allocation_id(self.allocation_id),
        )
        object.__setattr__(self, "pool_id", _normalize_pool_id(self.pool_id))
        object.__setattr__(self, "profile_name", _normalize_profile_name(self.profile_name))
        object.__setattr__(
            self,
            "consumer_kind",
            _normalize_consumer_kind(self.consumer_kind),
        )
        object.__setattr__(self, "consumer_id", _normalize_consumer_id(self.consumer_id))
        object.__setattr__(self, "target_host", _normalize_target_host(self.target_host))
        object.__setattr__(
            self,
            "status",
            _normalize_allocation_status(self.status),
        )
        object.__setattr__(self, "acquired_at", acquired_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "last_heartbeat_at", last_heartbeat_at)
        object.__setattr__(self, "released_at", released_at)
        object.__setattr__(
            self,
            "release_reason",
            _normalize_optional_text(self.release_reason),
        )
        object.__setattr__(
            self,
            "owned_target_ids",
            _normalize_target_ids(self.owned_target_ids),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))
        if self.status == "active" and self.released_at is not None:
            raise BrowserValidationError("active allocation must not define released_at.")
        if self.status != "active" and self.released_at is None:
            raise BrowserValidationError("inactive allocation must define released_at.")

    def is_active_at(self, now: datetime) -> bool:
        normalized_now = _ensure_aware_utc(now, label="now")
        return self.status == "active" and self.expires_at > normalized_now

    def matches_consumer(
        self,
        *,
        pool_id: str,
        consumer_kind: str,
        consumer_id: str,
        target_host: str | None = None,
    ) -> bool:
        return (
            self.pool_id == _normalize_pool_id(pool_id)
            and self.consumer_kind == _normalize_consumer_kind(consumer_kind)
            and self.consumer_id == _normalize_consumer_id(consumer_id)
            and self.target_host == _normalize_target_host(target_host)
        )
