from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.events.domain import EventCursor
from crxzipple.shared.time import coerce_utc_datetime

_DEFAULT_STUCK_SUBSCRIPTION_AFTER_SECONDS = 15.0
_DEFAULT_STALE_CHANNEL_RUNTIME_AFTER_SECONDS = 300.0


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


@dataclass(slots=True)
class OperationsActionService:
    events_service: Any
    channel_runtime_manager: Any
    daemon_manager: Any | None = None
    tool_service: Any | None = None
    skill_manager: Any | None = None
    access_service: Any | None = None
    access_inventory_collector: Any | None = None
    webhook_channel_runtime_service: Any | None = None
    memory_context_resolver: Any | None = None
    file_memory_service: Any | None = None
    orchestration_resume_service: Any | None = None
    orchestration_cancellation_service: Any | None = None

    def advance_event_subscriptions_to_head(
        self,
        *,
        subscription_id: str | None = None,
        source_topic: str | None = None,
        status: str = "stuck",
        observer_only: bool = False,
        stuck_after_seconds: float = _DEFAULT_STUCK_SUBSCRIPTION_AFTER_SECONDS,
        dry_run: bool = False,
        reason: str | None = None,
    ) -> EventSubscriptionAdvanceResult:
        normalized_subscription_id = _optional_text(subscription_id)
        normalized_source_topic = _optional_text(source_topic)
        normalized_status = _normalize_status_filter(status)
        states = self.events_service.list_subscription_cursors(
            source_topic=normalized_source_topic,
        )
        now = datetime.now(timezone.utc)
        items: list[EventSubscriptionAdvanceItem] = []
        advanced_count = 0
        skipped_count = 0

        for state in states:
            if (
                normalized_subscription_id is not None
                and state.subscription_id != normalized_subscription_id
            ):
                continue
            if observer_only and not state.subscription_id.startswith("operations.observer."):
                continue
            latest_cursor = self.events_service.snapshot_event_topic(state.source_topic)
            state_status = _subscription_status(
                state.cursor,
                latest_cursor,
                updated_at=getattr(state, "updated_at", None),
                now=now,
                stuck_after_seconds=stuck_after_seconds,
            )
            if not _status_matches(state_status, normalized_status):
                skipped_count += 1
                continue
            changed = _compare_cursors(state.cursor, latest_cursor) < 0
            if changed and not dry_run:
                self.events_service.set_subscription_cursor(
                    state.subscription_id,
                    source_topic=state.source_topic,
                    cursor=latest_cursor,
                )
                advanced_count += 1
            elif changed:
                advanced_count += 1
            else:
                skipped_count += 1
            items.append(
                EventSubscriptionAdvanceItem(
                    subscription_id=state.subscription_id,
                    source_topic=state.source_topic,
                    previous_cursor=state.cursor,
                    latest_cursor=latest_cursor,
                    status=state_status,
                    changed=changed,
                )
            )

        return EventSubscriptionAdvanceResult(
            matched_count=len(items),
            advanced_count=advanced_count,
            skipped_count=skipped_count,
            dry_run=dry_run,
            reason=_optional_text(reason),
            items=tuple(items),
        )

    def prune_stale_channel_runtimes(
        self,
        *,
        runtime_id: str | None = None,
        channel_type: str | None = None,
        stale_after_seconds: float = _DEFAULT_STALE_CHANNEL_RUNTIME_AFTER_SECONDS,
        dry_run: bool = False,
        reason: str | None = None,
    ) -> ChannelRuntimePruneResult:
        normalized_runtime_id = _optional_text(runtime_id)
        normalized_channel_type = _optional_text(channel_type)
        runtimes = self.channel_runtime_manager.list_runtimes(
            channel_type=normalized_channel_type,
        )
        now = datetime.now(timezone.utc)
        items: list[ChannelRuntimePruneItem] = []
        pruned_count = 0
        skipped_count = 0

        for runtime in runtimes:
            current_runtime_id = str(getattr(runtime, "runtime_id", "") or "").strip()
            if normalized_runtime_id is not None and current_runtime_id != normalized_runtime_id:
                continue
            heartbeat_age = _seconds_since(
                getattr(runtime, "last_heartbeat_at", None),
                now=now,
            )
            is_stale = heartbeat_age > max(float(stale_after_seconds), 0.0)
            status = "stale" if is_stale else _runtime_status(runtime)
            account_bindings = self.channel_runtime_manager.list_account_bindings(
                runtime_id=current_runtime_id,
            )
            connection_bindings = self.channel_runtime_manager.list_connection_bindings(
                runtime_id=current_runtime_id,
            )
            if is_stale:
                if not dry_run:
                    self.channel_runtime_manager.unregister_runtime(current_runtime_id)
                pruned_count += 1
            else:
                skipped_count += 1
            items.append(
                ChannelRuntimePruneItem(
                    runtime_id=current_runtime_id,
                    channel_type=str(getattr(runtime, "channel_type", "") or ""),
                    status=status,
                    heartbeat_age_seconds=heartbeat_age,
                    account_bindings_removed=len(account_bindings) if is_stale else 0,
                    connection_bindings_removed=len(connection_bindings) if is_stale else 0,
                    pruned=is_stale,
                )
            )

        return ChannelRuntimePruneResult(
            matched_count=len(items),
            pruned_count=pruned_count,
            skipped_count=skipped_count,
            dry_run=dry_run,
            reason=_optional_text(reason),
            items=tuple(items),
        )

    def run_daemon_service_action(
        self,
        *,
        service_key: str,
        action: str,
        reason: str,
    ) -> tuple[Any, ...]:
        manager = _required_dependency(self.daemon_manager, "daemon manager")
        normalized_action = str(action or "").strip().lower()
        if normalized_action == "ensure":
            return tuple(manager.ensure_service(service_key))
        if normalized_action == "healthcheck":
            return tuple(manager.healthcheck_service(service_key))
        if normalized_action == "reconcile":
            return tuple(manager.reconcile_service(service_key))
        if normalized_action == "stop":
            return tuple(manager.stop_service(service_key))
        raise ValueError(f"Unsupported daemon service action: {action}")

    def cancel_tool_run(self, *, run_id: str, reason: str | None = None) -> Any:
        return _required_dependency(self.tool_service, "tool service").cancel_tool_run(
            run_id,
        )

    async def retry_tool_run(self, *, run_id: str, reason: str | None = None) -> Any:
        return await _required_dependency(
            self.tool_service,
            "tool service",
        ).retry_tool_run(run_id)

    def prune_expired_tool_workers(
        self,
        *,
        retention_seconds: int = 3600,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return dict(
            _required_dependency(
                self.tool_service,
                "tool service",
            ).prune_expired_workers(retention_seconds=retention_seconds),
        )

    def replay_channel_dead_letter(
        self,
        *,
        channel_type: str,
        runtime_id: str | None = None,
        cursor: str | None = None,
        event_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if channel_type.strip().lower() != "webhook":
            raise ValueError(
                "Dead-letter replay no longer requeues generic legacy outbound events. "
                "Use the owning channel runtime replay path.",
            )
        return dict(
            _required_dependency(
                self.webhook_channel_runtime_service,
                "webhook channel runtime service",
            ).replay_dead_letter_record(
                runtime_id=runtime_id,
                cursor=cursor,
                event_id=event_id,
            ),
        )

    def validate_skill_package(self, *, path: str, reason: str | None = None) -> Any:
        return _required_dependency(self.skill_manager, "skill manager").validate(path=path)

    def install_global_skill(self, *, source_dir: str, reason: str | None = None) -> Any:
        from crxzipple.modules.skills.domain import SkillInstallScope

        return _required_dependency(self.skill_manager, "skill manager").install(
            source_dir=source_dir,
            scope=SkillInstallScope.GLOBAL,
            workspace_dir=None,
        )

    def collect_access_inventory(
        self,
        *,
        workspace_dir: str | None = None,
        include_ready: bool = True,
        include_disabled: bool = False,
    ) -> dict[str, Any]:
        collector = _required_dependency(
            self.access_inventory_collector,
            "access inventory collector",
        )
        return dict(
            collector(
                workspace_dir=workspace_dir,
                include_ready=include_ready,
                include_disabled=include_disabled,
            ),
        )

    def check_access_readiness(
        self,
        *,
        requirements: list[str],
        credential_bindings: list[str],
        workspace_dir: str | None = None,
        allow_literal_credentials: bool = False,
    ) -> list[tuple[str, Any]]:
        service = _required_dependency(self.access_service, "access service")
        checks: list[tuple[str, Any]] = []
        for requirement in requirements:
            readiness = service.check_requirement(requirement, workspace_dir=workspace_dir)
            checks.append(("requirement", readiness))
        for binding in credential_bindings:
            readiness = service.check_credential_binding(
                binding,
                workspace_dir=workspace_dir,
                allow_literal=allow_literal_credentials,
            )
            checks.append(("credential_binding", readiness))
        return checks

    def begin_access_setup(
        self,
        *,
        target: str,
        workspace_dir: str | None = None,
    ) -> Any:
        return _required_dependency(self.access_service, "access service").begin_setup(
            target,
            workspace_dir=workspace_dir,
        )

    def write_long_term_memory(
        self,
        *,
        agent_id: str,
        content: str,
        reason: str | None = None,
    ) -> Any:
        resolver = _required_dependency(
            self.memory_context_resolver,
            "memory context resolver",
        )
        context = resolver.resolve(agent_id)
        if context is None:
            raise LookupError("No file-backed memory context is available for this agent.")
        return _required_dependency(
            self.file_memory_service,
            "file memory service",
        ).write_long_term(context=context, content=content)

    def cancel_orchestration_run(
        self,
        *,
        run_id: str,
        reason: str | None = None,
    ) -> Any:
        return _required_dependency(
            self.orchestration_cancellation_service,
            "orchestration cancellation service",
        ).cancel_run(run_id, reason=reason)

    def resume_orchestration_run(
        self,
        *,
        run_id: str,
        reason: str | None = None,
    ) -> Any:
        from crxzipple.modules.orchestration.application.commands import (
            ResumeOrchestrationRunInput,
        )

        return _required_dependency(
            self.orchestration_resume_service,
            "orchestration resume service",
        ).resume_run(
            ResumeOrchestrationRunInput(
                run_id=run_id,
                reason=reason,
            ),
        )


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _required_dependency(value: Any, label: str) -> Any:
    if value is None:
        raise RuntimeError(f"Operations action dependency is not configured: {label}.")
    return value


def _normalize_status_filter(value: str | None) -> str:
    normalized = str(value or "stuck").strip().lower().replace("-", "_")
    if normalized not in {"all", "lagging", "stuck"}:
        return "stuck"
    return normalized


def _status_matches(status: str, filter_value: str) -> bool:
    if filter_value == "all":
        return True
    if filter_value == "lagging":
        return status in {"lagging", "stuck"}
    return status == "stuck"


def _subscription_status(
    cursor: EventCursor,
    latest_cursor: EventCursor,
    *,
    updated_at: Any,
    now: datetime,
    stuck_after_seconds: float,
) -> str:
    if _compare_cursors(cursor, latest_cursor) >= 0:
        return "at_head"
    if _seconds_since(updated_at, now=now) >= max(float(stuck_after_seconds), 0.0):
        return "stuck"
    return "lagging"


def _compare_cursors(left: str | None, right: str | None) -> int:
    left_cursor = _parse_cursor(left)
    right_cursor = _parse_cursor(right)
    if left_cursor == right_cursor:
        return 0
    return 1 if left_cursor > right_cursor else -1


def _parse_cursor(cursor: str | None) -> tuple[int, int]:
    raw = (cursor or "0-0").strip()
    if "-" not in raw:
        try:
            return (max(int(raw), 0), 0)
        except ValueError:
            return (0, 0)
    left, right = raw.split("-", 1)
    try:
        return (max(int(left), 0), max(int(right), 0))
    except ValueError:
        return (0, 0)


def _seconds_since(value: Any, *, now: datetime) -> float:
    if value is None:
        return float("inf")
    try:
        resolved = coerce_utc_datetime(value)
    except (TypeError, ValueError):
        return float("inf")
    return max(0.0, (now - resolved).total_seconds())


def _runtime_status(runtime: Any) -> str:
    raw = str(getattr(runtime, "status", "") or "online").strip().lower()
    if raw in {"online", "ready", "healthy"}:
        return "online"
    if raw in {"offline", "stopped"}:
        return "offline"
    if raw in {"error", "failed"}:
        return "error"
    return raw or "unknown"
