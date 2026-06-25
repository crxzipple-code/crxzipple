from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EventSubscriptionAdvanceItem:
    subscription_id: str
    source_topic: str
    previous_cursor: str
    latest_cursor: str
    status: str
    changed: bool


@dataclass(frozen=True, slots=True)
class EventSubscriptionAdvanceResult:
    matched_count: int
    advanced_count: int
    skipped_count: int
    dry_run: bool
    reason: str | None
    items: tuple[EventSubscriptionAdvanceItem, ...]


@dataclass(frozen=True, slots=True)
class ChannelRuntimePruneItem:
    runtime_id: str
    channel_type: str
    status: str
    heartbeat_age_seconds: float
    account_bindings_removed: int
    connection_bindings_removed: int
    pruned: bool


@dataclass(frozen=True, slots=True)
class ChannelRuntimePruneResult:
    matched_count: int
    pruned_count: int
    skipped_count: int
    dry_run: bool
    reason: str | None
    items: tuple[ChannelRuntimePruneItem, ...]
