from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from crxzipple.modules.operations.interfaces.http_models_action_base import (
    OperationsActionRequest,
)


class OperationsEventSubscriptionAdvanceRequest(OperationsActionRequest):
    subscription_id: str | None = None
    source_topic: str | None = None
    status: str = "stuck"
    observer_only: bool = False
    dry_run: bool = False


class OperationsEventSubscriptionAdvanceItemResponse(BaseModel):
    subscription_id: str
    source_topic: str
    previous_cursor: str
    latest_cursor: str
    status: str
    changed: bool


class OperationsEventSubscriptionAdvanceResponse(BaseModel):
    matched_count: int
    advanced_count: int
    skipped_count: int
    dry_run: bool
    reason: str | None = None
    items: list[OperationsEventSubscriptionAdvanceItemResponse]

    @classmethod
    def from_result(cls, result: Any) -> "OperationsEventSubscriptionAdvanceResponse":
        return cls(
            matched_count=result.matched_count,
            advanced_count=result.advanced_count,
            skipped_count=result.skipped_count,
            dry_run=result.dry_run,
            reason=result.reason,
            items=[
                OperationsEventSubscriptionAdvanceItemResponse(
                    subscription_id=item.subscription_id,
                    source_topic=item.source_topic,
                    previous_cursor=item.previous_cursor,
                    latest_cursor=item.latest_cursor,
                    status=item.status,
                    changed=item.changed,
                )
                for item in result.items
            ],
        )


class OperationsChannelDeadLetterReplayRequest(OperationsActionRequest):
    runtime_id: str | None = None
    cursor: str | None = None
    event_id: str | None = None


class OperationsChannelRuntimePruneRequest(OperationsActionRequest):
    runtime_id: str | None = None
    channel_type: str | None = None
    stale_after_seconds: float = 300.0
    dry_run: bool = False


class OperationsChannelRuntimePruneItemResponse(BaseModel):
    runtime_id: str
    channel_type: str
    status: str
    heartbeat_age_seconds: float
    account_bindings_removed: int
    connection_bindings_removed: int
    pruned: bool


class OperationsChannelRuntimePruneResponse(BaseModel):
    matched_count: int
    pruned_count: int
    skipped_count: int
    dry_run: bool
    reason: str | None = None
    items: list[OperationsChannelRuntimePruneItemResponse]

    @classmethod
    def from_result(cls, result: Any) -> "OperationsChannelRuntimePruneResponse":
        return cls(
            matched_count=result.matched_count,
            pruned_count=result.pruned_count,
            skipped_count=result.skipped_count,
            dry_run=result.dry_run,
            reason=result.reason,
            items=[
                OperationsChannelRuntimePruneItemResponse(
                    runtime_id=item.runtime_id,
                    channel_type=item.channel_type,
                    status=item.status,
                    heartbeat_age_seconds=item.heartbeat_age_seconds,
                    account_bindings_removed=item.account_bindings_removed,
                    connection_bindings_removed=item.connection_bindings_removed,
                    pruned=item.pruned,
                )
                for item in result.items
            ],
        )
