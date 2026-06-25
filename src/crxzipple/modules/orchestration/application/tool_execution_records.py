from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.tool_resource_policy import (
    ToolResourcePolicy,
)
from crxzipple.modules.orchestration.domain import PendingApprovalRequest
from crxzipple.modules.tool.domain import ToolExecutionTarget, ToolRun


@dataclass(frozen=True, slots=True)
class ToolRunLink:
    tool_call_id: str
    tool_name: str
    tool_run_id: str
    tool_id: str
    status: str
    mode: str
    strategy: str
    environment: str
    call_session_item_id: str | None = None
    result_session_item_id: str | None = None
    background: bool = False
    tool_execution_plan: dict[str, object] = field(default_factory=dict)
    tool_lifecycle: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "tool_run_id": self.tool_run_id,
            "tool_id": self.tool_id,
            "status": self.status,
            "mode": self.mode,
            "strategy": self.strategy,
            "environment": self.environment,
            "call_session_item_id": self.call_session_item_id,
            "result_session_item_id": self.result_session_item_id,
            "background": self.background,
        }
        if self.tool_execution_plan:
            payload["tool_execution_plan"] = dict(self.tool_execution_plan)
        if self.tool_lifecycle:
            payload["tool_lifecycle"] = dict(self.tool_lifecycle)
        return payload


@dataclass(frozen=True, slots=True)
class PreparedToolExecution:
    tool_call: ToolCallIntent
    tool_id: str
    target: ToolExecutionTarget
    resource_policy: ToolResourcePolicy
    tool_surface_id: str | None = None
    plan: "ToolExecutionPlan | None" = None


@dataclass(frozen=True, slots=True)
class ToolExecutionPlan:
    tool_call_id: str
    tool_name: str
    tool_id: str
    mode: str
    strategy: str
    environment: str
    tool_surface_id: str | None = None
    resource_policy: dict[str, object] = field(default_factory=dict)
    arguments_digest: str | None = None

    @classmethod
    def from_execution(
        cls,
        prepared: PreparedToolExecution,
    ) -> "ToolExecutionPlan":
        tool_call = prepared.tool_call
        target = prepared.target
        resource_policy = prepared.resource_policy
        return cls(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            tool_id=prepared.tool_id,
            mode=target.mode.value,
            strategy=target.strategy.value,
            environment=target.environment.value,
            tool_surface_id=prepared.tool_surface_id,
            resource_policy=resource_policy.to_payload(),
            arguments_digest=arguments_digest(tool_call.arguments),
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "tool_id": self.tool_id,
            "mode": self.mode,
            "strategy": self.strategy,
            "environment": self.environment,
        }
        if self.resource_policy:
            payload["resource_policy"] = dict(self.resource_policy)
        if self.tool_surface_id is not None:
            payload["tool_surface_id"] = self.tool_surface_id
        if self.arguments_digest is not None:
            payload["arguments_digest"] = self.arguments_digest
        return payload


@dataclass(frozen=True, slots=True)
class ToolExecutionBatchOutcome:
    tool_call_session_item_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_result_session_item_ids: tuple[str, ...] = field(default_factory=tuple)
    inline_runs: tuple[ToolRun, ...] = field(default_factory=tuple)
    background_runs: tuple[tuple[ToolCallIntent, ToolRun], ...] = field(
        default_factory=tuple,
    )
    tool_run_links: tuple[ToolRunLink, ...] = field(default_factory=tuple)
    tool_execution_plans: tuple[ToolExecutionPlan, ...] = field(default_factory=tuple)
    pending_approval_request: PendingApprovalRequest | None = None
    yield_requested: bool = False
    yield_reason: str | None = None


@dataclass(slots=True)
class ToolExecutionBatchState:
    tool_call_session_item_ids: list[str] = field(default_factory=list)
    tool_result_session_item_ids: list[str] = field(default_factory=list)
    inline_runs: list[ToolRun] = field(default_factory=list)
    background_runs: list[tuple[ToolCallIntent, ToolRun]] = field(default_factory=list)
    tool_run_links: list[ToolRunLink] = field(default_factory=list)
    tool_execution_plans: list[ToolExecutionPlan] = field(default_factory=list)
    prepared_executions: list[PreparedToolExecution] = field(default_factory=list)
    pending_tool_call_messages: list[ToolCallIntent] = field(default_factory=list)
    tool_call_session_item_id_by_call_id: dict[str, str] = field(default_factory=dict)
    yield_requested: bool = False
    yield_reason: str | None = None
    stop_remaining_batches: bool = False

    @classmethod
    def from_tool_call_session_item_ids(
        cls,
        value: dict[str, str] | None,
    ) -> "ToolExecutionBatchState":
        return cls(
            tool_call_session_item_id_by_call_id=dict(value or {}),
        )

    def request_yield(self, reason: str | None) -> None:
        self.yield_requested = True
        if self.yield_reason is None and reason is not None:
            self.yield_reason = reason

    def stop_remaining(self) -> None:
        self.stop_remaining_batches = True

    def clear_pending_dispatch(self) -> None:
        self.prepared_executions.clear()
        self.pending_tool_call_messages.clear()

    def outcome(
        self,
        *,
        pending_approval_request: PendingApprovalRequest | None = None,
    ) -> ToolExecutionBatchOutcome:
        return ToolExecutionBatchOutcome(
            tool_call_session_item_ids=tuple(self.tool_call_session_item_ids),
            tool_result_session_item_ids=tuple(self.tool_result_session_item_ids),
            inline_runs=tuple(self.inline_runs),
            background_runs=tuple(self.background_runs),
            tool_run_links=tuple(self.tool_run_links),
            tool_execution_plans=tuple(self.tool_execution_plans),
            pending_approval_request=pending_approval_request,
            yield_requested=self.yield_requested,
            yield_reason=self.yield_reason,
        )


def tool_lifecycle_from_tool_run(tool_run: ToolRun) -> dict[str, object]:
    payload: dict[str, object] = {}
    for source in tool_lifecycle_sources(tool_run):
        for key in (
            "superseded",
            "superseded_by_tool_call_id",
            "replaced_by_tool_call_id",
            "replacement_tool_call_id",
            "supersedes_tool_call_id",
            "supersedes_tool_run_id",
            "supersedes_result_session_item_id",
            "lifecycle_status",
            "evidence_lifecycle_status",
            "evidence_lifecycle",
        ):
            if key in source:
                payload[key] = source[key]
    return payload


def arguments_digest(arguments: dict[str, object]) -> str:
    try:
        payload = json.dumps(
            arguments,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except TypeError:
        payload = repr(sorted(arguments.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def tool_lifecycle_sources(tool_run: ToolRun) -> tuple[dict[str, object], ...]:
    sources: list[dict[str, object]] = []
    sources.extend(_nested_tool_lifecycle_sources(tool_run.metadata))
    result_payload = tool_run.result_payload
    if isinstance(result_payload, dict):
        sources.extend(_nested_tool_lifecycle_sources(result_payload))
        for key in ("metadata", "details"):
            sources.extend(_nested_tool_lifecycle_sources(result_payload.get(key)))
    return tuple(sources)


def _nested_tool_lifecycle_sources(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, dict):
        return ()
    sources: list[dict[str, object]] = []
    for key in ("tool_lifecycle", "evidence_lifecycle"):
        nested = value.get(key)
        if isinstance(nested, dict):
            sources.append(nested)
    return tuple(sources)
