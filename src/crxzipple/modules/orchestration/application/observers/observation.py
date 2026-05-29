from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.ports import (
    EventPublishPort,
    OrchestrationExecutorLeaseQueryPort,
    OrchestrationRunLookupPort,
    OrchestrationRunQueryPort,
    ToolExecutionPort,
)
from crxzipple.modules.orchestration.domain import OrchestrationRunNotFoundError
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationExecutorLeaseStatus,
    OrchestrationRunStatus,
    utcnow,
)
from crxzipple.modules.tool.domain.exceptions import ToolRunNotFoundError
from crxzipple.shared.domain.events import Event
from crxzipple.shared.orchestration_observation import (
    ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT,
    ORCHESTRATION_RUN_OBSERVATION_EVENT_NAMES,
    ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
    ORCHESTRATION_RUNTIME_STATUS_EVENT,
    TOOL_RUN_OBSERVATION_SOURCE_EVENT_NAMES,
)
from crxzipple.shared.time import (
    coerce_utc_datetime,
    format_datetime_utc,
)

logger = get_logger(__name__)


RUN_OBSERVATION_EVENT_NAMES = ORCHESTRATION_RUN_OBSERVATION_EVENT_NAMES
TOOL_OBSERVATION_SOURCE_EVENT_NAMES = TOOL_RUN_OBSERVATION_SOURCE_EVENT_NAMES


def turn_session_topic(session_key: str) -> str:
    normalized = session_key.strip()
    if not normalized:
        raise ValueError("session_key is required to build a turn session topic.")
    return f"turn.session.{normalized}"


def turn_session_live_topic(session_key: str) -> str:
    normalized = session_key.strip()
    if not normalized:
        raise ValueError("session_key is required to build a live turn session topic.")
    return f"turn.live.session.{normalized}"


def orchestration_runtime_observation_topic() -> str:
    return "orchestration.runtime_observation"


def _optional_isoformat(value: object) -> str | None:
    return _optional_timestamp(value)


def _status_value(value: object) -> str:
    raw_value = getattr(value, "value", value)
    return str(raw_value)


def _optional_timestamp(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if callable(isoformat):
        return str(isoformat())
    return str(value)


def _age_seconds(value: object, *, now: datetime) -> float | None:
    if not isinstance(value, datetime):
        return None
    timestamp = coerce_utc_datetime(value)
    comparison_now = coerce_utc_datetime(now)
    return max((comparison_now - timestamp).total_seconds(), 0.0)


def _compact_metric_groups(
    leases: list[object],
    *,
    prefixes: tuple[str, ...],
) -> dict[str, list[dict[str, object]]]:
    groups: dict[str, list[dict[str, object]]] = {
        "counters": [],
        "gauges": [],
        "timings": [],
    }
    for lease in leases:
        metadata = getattr(lease, "metadata", None)
        if not isinstance(metadata, dict):
            continue
        runtime_metrics = metadata.get("runtime_metrics")
        if not isinstance(runtime_metrics, dict):
            continue
        worker_id = str(getattr(lease, "worker_id", getattr(lease, "id", "")) or "")
        for group_name in groups:
            raw_items = runtime_metrics.get(group_name)
            if not isinstance(raw_items, list):
                continue
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    continue
                metric_name = str(raw_item.get("name") or "")
                if not any(metric_name.startswith(prefix) for prefix in prefixes):
                    continue
                item = dict(raw_item)
                if worker_id:
                    item["worker_id"] = worker_id
                groups[group_name].append(item)
    return groups


@dataclass(slots=True)
class RunObservationObserver:
    events_service: EventPublishPort
    run_lookup: OrchestrationRunLookupPort

    def observe_run_event(self, event: Event) -> None:
        run_id = event.payload.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            logger.debug(
                "skipping run observation observation without run_id",
                extra={"event_name": event.name, "payload": event.payload},
            )
            return
        try:
            run = self.run_lookup.get_run(run_id)
        except OrchestrationRunNotFoundError:
            logger.debug(
                "skipping run observation observation for missing run",
                extra={"event_name": event.name, "run_id": run_id},
            )
            return
        payload = {
            "event_name": event.name,
            "run_id": run.id,
            "session_key": run.session_key,
            "active_session_id": run.active_session_id,
            "status": run.status.value,
            "stage": run.stage.value,
            "current_step": run.current_step,
            "waiting_reason": run.waiting_reason,
            "pending_tool_run_ids": list(run.pending_tool_run_ids),
            "pending_approval_request": (
                dict(run.metadata.get("pending_approval_request"))
                if isinstance(run.metadata.get("pending_approval_request"), dict)
                else None
            ),
            "last_approval_resolution": (
                dict(run.metadata.get("last_approval_resolution"))
                if isinstance(run.metadata.get("last_approval_resolution"), dict)
                else None
            ),
        }
        if run.session_key is None:
            logger.debug(
                "skipping run observation observation without session key",
                extra={"event_name": event.name, "run_id": run.id},
            )
            return
        dedupe_key = (
            f"{event.name}:{run.id}:{_optional_timestamp(run.updated_at)}"
            if run.updated_at is not None
            else f"{event.name}:{run.id}"
        )
        self.events_service.publish(
            Event(
                topic=turn_session_topic(run.session_key),
                kind="fact",
                ordering_key=run.id,
                dedupe_key=dedupe_key,
                payload=payload,
            ),
        )


@dataclass(slots=True)
class SessionMessageObservationObserver:
    events_service: EventPublishPort

    def observe_message_appended(self, event: Event) -> None:
        session_key = event.payload.get("session_key")
        message_id = event.payload.get("message_id")
        if (
            not isinstance(message_id, str)
            or not message_id.strip()
            or not isinstance(session_key, str)
            or not session_key.strip()
        ):
            logger.debug(
                "skipping message observation observation without complete message fact",
                extra={"event_name": event.name, "payload": event.payload},
            )
            return
        payload = {
            "event_name": ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT,
            **dict(event.payload),
        }
        self.events_service.publish(
            Event(
                topic=turn_session_topic(session_key),
                kind="fact",
                ordering_key=session_key,
                dedupe_key=f"{event.name}:{message_id}",
                payload=payload,
            ),
        )


@dataclass(slots=True)
class ToolRunObservationObserver:
    events_service: EventPublishPort
    run_lookup: OrchestrationRunLookupPort
    tool_execution_port: ToolExecutionPort

    def observe_tool_event(self, event: Event) -> None:
        tool_run_id = event.payload.get("run_id")
        if not isinstance(tool_run_id, str) or not tool_run_id.strip():
            logger.debug(
                "skipping tool observation observation without tool run id",
                extra={"event_name": event.name, "payload": event.payload},
            )
            return
        try:
            tool_run = self.tool_execution_port.get_tool_run(tool_run_id)
        except ToolRunNotFoundError:
            logger.debug(
                "skipping tool observation observation for missing tool run",
                extra={"event_name": event.name, "tool_run_id": tool_run_id},
            )
            return
        invocation_context = tool_run.invocation_context
        orchestration_run_id = (
            invocation_context.get_str("run_id") if invocation_context is not None else None
        )
        session_key = (
            invocation_context.get_str("session_key")
            if invocation_context is not None
            else None
        )
        if orchestration_run_id is None or session_key is None:
            logger.debug(
                "skipping tool observation observation without orchestration context",
                extra={
                    "event_name": event.name,
                    "tool_run_id": tool_run_id,
                    "invocation_context": (
                        dict(invocation_context.attrs)
                        if invocation_context is not None
                        else None
                    ),
                },
            )
            return
        active_session_id: str | None = None
        try:
            run = self.run_lookup.get_run(orchestration_run_id)
        except OrchestrationRunNotFoundError:
            run = None
        if run is not None:
            active_session_id = run.active_session_id
            if run.session_key is not None and run.session_key.strip():
                session_key = run.session_key
        payload = {
            "event_name": ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
            "source_event_name": event.event_name or event.name,
            "run_id": orchestration_run_id,
            "session_key": session_key,
            "active_session_id": active_session_id,
            "tool_run_id": tool_run.id,
            "tool_id": tool_run.tool_id,
            "tool_name": tool_run.tool_id,
            "tool_status": tool_run.status.value,
            "tool_mode": tool_run.target.mode.value,
            "tool_strategy": tool_run.target.strategy.value,
            "tool_environment": tool_run.target.environment.value,
            "attempt_count": tool_run.attempt_count,
            "max_attempts": tool_run.max_attempts,
            "output_payload": tool_run.output_payload,
            "error_message": tool_run.error_message,
            "created_at": _optional_isoformat(tool_run.created_at),
            "started_at": _optional_isoformat(tool_run.started_at),
            "completed_at": _optional_isoformat(tool_run.completed_at),
        }
        self.events_service.publish(
            Event(
                topic=turn_session_topic(session_key),
                kind="fact",
                ordering_key=orchestration_run_id,
                dedupe_key=(
                    f"{payload['source_event_name']}:{tool_run.id}:"
                    f"{tool_run.attempt_count}:{tool_run.status.value}"
                ),
                payload=payload,
            ),
        )


@dataclass(slots=True)
class RuntimeObservationObserver:
    events_service: EventPublishPort
    run_query: OrchestrationRunQueryPort
    executor_lease_query: OrchestrationExecutorLeaseQueryPort

    def observe_runtime_event(self, event: Event) -> None:
        now = utcnow()
        queued_runs = self.run_query.list_runs(
            status=OrchestrationRunStatus.QUEUED,
        )
        running_runs = self.run_query.list_runs(
            status=OrchestrationRunStatus.RUNNING,
        )
        waiting_runs = self.run_query.list_runs(
            status=OrchestrationRunStatus.WAITING,
        )
        leases = self.executor_lease_query.list_executor_leases(status=None)
        metric_leases = self._metric_leases(leases, now=now)
        source_event_name = event.event_name or event.name or ""
        payload = {
            "event_name": ORCHESTRATION_RUNTIME_STATUS_EVENT,
            "source_event_name": source_event_name,
            "source_event_id": event.id,
            "observed_at": format_datetime_utc(now),
            "queue": self._queue_payload(
                queued_runs=queued_runs,
                running_runs=running_runs,
                waiting_runs=waiting_runs,
                now=now,
            ),
            "lanes": self._lanes_payload(
                queued_runs=queued_runs,
                running_runs=running_runs,
                waiting_runs=waiting_runs,
            ),
            "executor": self._executor_payload(leases=leases, now=now),
            "llm": {
                "profile_limiter_metrics": _compact_metric_groups(
                    metric_leases,
                    prefixes=("llm.profile_limiter.",),
                ),
            },
        }
        self.events_service.publish(
            Event(
                topic=orchestration_runtime_observation_topic(),
                kind="fact",
                ordering_key="orchestration.runtime",
                dedupe_key=f"{ORCHESTRATION_RUNTIME_STATUS_EVENT}:{event.id}",
                payload=payload,
            ),
        )

    @staticmethod
    def _queue_payload(
        *,
        queued_runs: list[Any],
        running_runs: list[Any],
        waiting_runs: list[Any],
        now: datetime,
    ) -> dict[str, object]:
        oldest_queued_at: datetime | None = None
        queued_by_policy: dict[str, int] = {}
        queued_by_priority: dict[str, int] = {}
        waiting_by_reason: dict[str, int] = {}
        for run in queued_runs:
            policy = _status_value(getattr(run, "queue_policy", "unknown"))
            queued_by_policy[policy] = queued_by_policy.get(policy, 0) + 1
            priority = str(getattr(run, "priority", "unknown"))
            queued_by_priority[priority] = queued_by_priority.get(priority, 0) + 1
            queued_at = getattr(run, "queued_at", None)
            if isinstance(queued_at, datetime) and (
                oldest_queued_at is None or queued_at < oldest_queued_at
            ):
                oldest_queued_at = queued_at
        for run in waiting_runs:
            reason = str(getattr(run, "waiting_reason", "") or "unknown")
            waiting_by_reason[reason] = waiting_by_reason.get(reason, 0) + 1
        return {
            "queued_run_count": len(queued_runs),
            "running_run_count": len(running_runs),
            "waiting_run_count": len(waiting_runs),
            "oldest_queued_at": _optional_timestamp(oldest_queued_at),
            "oldest_queued_age_seconds": _age_seconds(oldest_queued_at, now=now),
            "queued_by_policy": dict(sorted(queued_by_policy.items())),
            "queued_by_priority": dict(sorted(queued_by_priority.items())),
            "waiting_by_reason": dict(sorted(waiting_by_reason.items())),
        }

    @staticmethod
    def _lanes_payload(
        *,
        queued_runs: list[Any],
        running_runs: list[Any],
        waiting_runs: list[Any],
    ) -> dict[str, object]:
        active_lane_counts: dict[str, int] = {}
        queued_lane_counts: dict[str, int] = {}
        unlanned_queued_run_count = 0
        unlanned_active_run_count = 0
        for run in (*running_runs, *waiting_runs):
            lane_key = getattr(run, "lane_key", None)
            if isinstance(lane_key, str) and lane_key.strip():
                normalized = lane_key.strip()
                active_lane_counts[normalized] = active_lane_counts.get(normalized, 0) + 1
            else:
                unlanned_active_run_count += 1
        for run in queued_runs:
            lane_key = getattr(run, "lane_key", None)
            if isinstance(lane_key, str) and lane_key.strip():
                normalized = lane_key.strip()
                queued_lane_counts[normalized] = queued_lane_counts.get(normalized, 0) + 1
            else:
                unlanned_queued_run_count += 1
        blocked_lanes = [
            {
                "lane_key": lane_key,
                "queued_run_count": queued_count,
                "active_run_count": active_lane_counts.get(lane_key, 0),
            }
            for lane_key, queued_count in queued_lane_counts.items()
            if active_lane_counts.get(lane_key, 0) > 0
        ]
        blocked_lanes.sort(
            key=lambda item: (
                -int(item["queued_run_count"]),
                str(item["lane_key"]),
            ),
        )
        queued_lanes = [
            {
                "lane_key": lane_key,
                "queued_run_count": queued_count,
                "active_run_count": active_lane_counts.get(lane_key, 0),
            }
            for lane_key, queued_count in queued_lane_counts.items()
        ]
        queued_lanes.sort(
            key=lambda item: (
                -int(item["queued_run_count"]),
                str(item["lane_key"]),
            ),
        )
        return {
            "active_lane_count": len(active_lane_counts),
            "queued_lane_count": len(queued_lane_counts),
            "blocked_lane_count": len(blocked_lanes),
            "unlanned_active_run_count": unlanned_active_run_count,
            "unlanned_queued_run_count": unlanned_queued_run_count,
            "blocked_lanes": blocked_lanes[:10],
            "queued_lanes": queued_lanes[:10],
        }

    @staticmethod
    def _executor_payload(
        *,
        leases: list[Any],
        now: datetime,
    ) -> dict[str, object]:
        online_executor_count = 0
        capacity_executor_count = 0
        total_max_inflight_assignments = 0
        total_inflight_assignment_count = 0
        expired_lease_count = 0
        visible_lease_count = 0
        effective_status_counts: dict[str, int] = {}
        lease_payloads: list[dict[str, object]] = []
        for lease in leases:
            status = _status_value(getattr(lease, "status", "unknown"))
            expired = RuntimeObservationObserver._lease_is_expired(lease, now=now)
            effective_status = RuntimeObservationObserver._lease_effective_status(
                lease,
                expired=expired,
                status=status,
                now=now,
            )
            effective_status_counts[effective_status] = (
                effective_status_counts.get(effective_status, 0) + 1
            )
            if expired:
                expired_lease_count += 1
            counts_toward_capacity = (
                effective_status == OrchestrationExecutorLeaseStatus.ONLINE.value
            )
            max_inflight = int(getattr(lease, "max_inflight_assignments", 0) or 0)
            inflight = int(getattr(lease, "inflight_assignment_count", 0) or 0)
            available = max(max_inflight - inflight, 0) if counts_toward_capacity else 0
            if counts_toward_capacity:
                online_executor_count += 1
                capacity_executor_count += 1
                total_max_inflight_assignments += max_inflight
                total_inflight_assignment_count += inflight
            if expired and inflight <= 0:
                continue
            visible_lease_count += 1
            lease_payloads.append(
                RuntimeObservationObserver._lease_payload(
                    lease,
                    status=status,
                    effective_status=effective_status,
                    expired=expired,
                    counts_toward_capacity=counts_toward_capacity,
                    max_inflight=max_inflight,
                    inflight=inflight,
                    available=available,
                ),
            )
        lease_payloads.sort(
            key=lambda item: (
                not bool(item.get("counts_toward_capacity")),
                bool(item.get("expired")),
                str(item.get("worker_id") or ""),
            ),
        )
        return {
            "lease_count": len(leases),
            "visible_lease_count": visible_lease_count,
            "expired_lease_count": expired_lease_count,
            "effective_status_counts": dict(sorted(effective_status_counts.items())),
            "online_executor_count": online_executor_count,
            "capacity_executor_count": capacity_executor_count,
            "total_max_inflight_assignments": total_max_inflight_assignments,
            "total_inflight_assignment_count": total_inflight_assignment_count,
            "total_available_assignment_slots": max(
                total_max_inflight_assignments - total_inflight_assignment_count,
                0,
            ),
            "leases": lease_payloads,
        }

    @staticmethod
    def _lease_is_expired(lease: Any, *, now: datetime) -> bool:
        is_expired = getattr(lease, "is_expired", None)
        if not callable(is_expired):
            return False
        try:
            return bool(is_expired(now=now))
        except TypeError:
            return bool(is_expired())

    @staticmethod
    def _metric_leases(leases: list[Any], *, now: datetime) -> list[Any]:
        return [
            lease
            for lease in leases
            if not RuntimeObservationObserver._lease_is_expired(lease, now=now)
            or int(getattr(lease, "inflight_assignment_count", 0) or 0) > 0
        ]

    @staticmethod
    def _lease_effective_status(
        lease: Any,
        *,
        expired: bool,
        status: str,
        now: datetime,
    ) -> str:
        effective_status = getattr(lease, "effective_status", None)
        if callable(effective_status):
            try:
                return _status_value(effective_status(now=now))
            except TypeError:
                return _status_value(effective_status())
        return OrchestrationExecutorLeaseStatus.OFFLINE.value if expired else status

    @staticmethod
    def _lease_payload(
        lease: Any,
        *,
        status: str,
        effective_status: str,
        expired: bool,
        counts_toward_capacity: bool,
        max_inflight: int,
        inflight: int,
        available: int,
    ) -> dict[str, object]:
        metadata = getattr(lease, "metadata", None)
        runtime_state = metadata.get("runtime_state") if isinstance(metadata, dict) else None
        runtime_metrics = metadata.get("runtime_metrics") if isinstance(metadata, dict) else None
        return {
            "worker_id": str(getattr(lease, "worker_id", getattr(lease, "id", "")) or ""),
            "status": status,
            "effective_status": effective_status,
            "expired": expired,
            "counts_toward_capacity": counts_toward_capacity,
            "max_inflight_assignments": max_inflight,
            "inflight_assignment_count": inflight,
            "available_assignment_slots": available,
            "last_heartbeat_at": _optional_timestamp(
                getattr(lease, "last_heartbeat_at", None),
            ),
            "lease_expires_at": _optional_timestamp(
                getattr(lease, "lease_expires_at", None),
            ),
            "runtime_state": runtime_state if isinstance(runtime_state, dict) else None,
            "runtime_metrics": runtime_metrics if isinstance(runtime_metrics, dict) else None,
        }
