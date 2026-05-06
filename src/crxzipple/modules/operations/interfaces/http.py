from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.authorization import authorize_tool_run
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.events import EventTopicRecord, EventTopicWatch
from crxzipple.modules.operations.interfaces.http_models import (
    AccessOperationsResponse,
    OperationsChannelRuntimePruneRequest,
    OperationsChannelRuntimePruneResponse,
    OperationsActionAuditResponse,
    OperationsActionReasonRequest,
    OperationsActionRequest,
    OperationsAccessCheckRequest,
    OperationsChannelDeadLetterReplayRequest,
    OperationsDaemonServiceActionRequest,
    OperationsEventSubscriptionAdvanceRequest,
    OperationsEventSubscriptionAdvanceResponse,
    OperationsMemoryWriteLongTermRequest,
    OperationsMemoryWriteResultResponse,
    ChannelsOperationsResponse,
    DaemonOperationsResponse,
    EventsOperationsResponse,
    LlmOperationsResponse,
    MemoryOperationsResponse,
    OperationsModulePageResponse,
    OperationsModuleOverviewResponse,
    OperationsRuntimeStatusItemResponse,
    OperationsRuntimeStatusResponse,
    OperationsSkillInstallRequest,
    OperationsSkillValidateRequest,
    LlmInvocationDetailResponse,
    OperationsToolRunActionResponse,
    OperationsToolWorkerPruneRequest,
    OperationsToolWorkerPruneResponse,
    OrchestrationOperationsResponse,
    SkillsOperationsResponse,
    ToolRunDetailResponse,
    ToolOperationsResponse,
)
from crxzipple.modules.operations.application.read_models.llm import (
    defer_llm_invocation_details_payload,
)
from crxzipple.modules.operations.application.read_models.tool import (
    defer_tool_run_details_payload,
)
from crxzipple.modules.operations.application.actions import OperationsActionService
from crxzipple.modules.access.interfaces.inventory import collect_access_inventory
from crxzipple.modules.access.interfaces.presenters import (
    present_readiness,
    present_setup_flow,
)
from crxzipple.modules.daemon import DaemonNotFoundError, DaemonValidationError
from crxzipple.modules.daemon.interfaces.presenters import instance_payload
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.modules.skills.domain import SkillError
from crxzipple.modules.tool.domain.exceptions import (
    ToolRunNotFoundError,
    ToolValidationError,
)
from crxzipple.shared.time import format_datetime_utc, format_optional_datetime_utc


router = APIRouter()

_PROJECTED_MODULES = frozenset(
    {
        "orchestration",
        "tool",
        "llm",
        "access",
        "channels",
        "memory",
        "skills",
        "events",
        "daemon",
    },
)
_TOOL_ACTIVE_STATUSES = frozenset(
    {"created", "queued", "dispatching", "running", "waiting", "cancel_requested"}
)
_TOOL_WAITING_STATUSES = _TOOL_ACTIVE_STATUSES - {"running"}
_TOOL_LONG_RUNNING_SECONDS = 300
_OPERATIONS_STREAM_TOPIC = "events.named.operations.projection.invalidated"
_OPERATIONS_STREAM_DISCOVERY_INTERVAL_SECONDS = 0.25


def _operations_action_service(container: AppContainer) -> OperationsActionService:
    return OperationsActionService(
        events_service=container.events_service,
        channel_runtime_manager=container.channel_runtime_manager,
        daemon_manager=container.daemon_manager,
        tool_service=container.tool_service,
        skill_manager=container.skill_manager,
        access_service=container.access_service,
        access_inventory_collector=lambda **kwargs: collect_access_inventory(
            container,
            **kwargs,
        ),
        webhook_channel_runtime_service=container.webhook_channel_runtime_service,
        memory_context_resolver=container.memory_context_resolver,
        file_memory_service=container.file_memory_service,
        orchestration_resume_service=container.orchestration_scheduler_service,
        orchestration_cancellation_service=container.orchestration_cancellation_service,
    )


@router.get("/runtime", response_model=OperationsRuntimeStatusResponse)
def get_operations_runtime_status(
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsRuntimeStatusResponse:
    return _runtime_status(container)


@router.get("/stream")
def stream_operations_refresh_feed(
    container: Annotated[AppContainer, Depends(get_container)],
    snapshot_limit: Annotated[int, Query(ge=0, le=50)] = 0,
    timeout_seconds: Annotated[float, Query(gt=0.0, le=300.0)] = 120.0,
) -> StreamingResponse:
    events_service = container.events_service
    if events_service is None:
        raise HTTPException(status_code=503, detail="Event service is not available.")

    def event_stream():
        cursor = events_service.snapshot_event_topic(_OPERATIONS_STREAM_TOPIC)
        yield _format_operations_sse_event(
            "connected",
            {
                "event_type": "connected",
                "modules": [],
                "stream_role": "operations",
                "stream_scope": "projection_refresh",
            },
        )
        if snapshot_limit > 0:
            records = events_service.read_recent_event_topic(
                _OPERATIONS_STREAM_TOPIC,
                limit=snapshot_limit,
            )
            yield _format_operations_sse_event(
                "snapshot",
                {
                    "event_type": "snapshot",
                    "modules": [],
                    "records": [
                        _operations_stream_record_payload(record)
                        for record in records
                    ],
                },
            )

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            records = events_service.read_event_topic(
                _OPERATIONS_STREAM_TOPIC,
                after_cursor=cursor,
                limit=100,
            )
            if records:
                cursor = records[-1].cursor
                for record in records:
                    yield _format_operations_sse_event(
                        "projection_updated",
                        _operations_stream_record_payload(record),
                    )
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            events_service.wait_for_event_topics(
                (
                    EventTopicWatch(
                        topic=_OPERATIONS_STREAM_TOPIC,
                        after_cursor=cursor,
                    ),
                ),
                timeout_seconds=min(
                    remaining,
                    _OPERATIONS_STREAM_DISCOVERY_INTERVAL_SECONDS,
                ),
            )
        yield _format_operations_sse_event(
            "timeout",
            {
                "event_type": "timeout",
                "modules": [],
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Crx-Stream-Role": "operations",
            "X-Crx-Stream-Scope": "projection_refresh",
        },
    )


@router.get("/orchestration", response_model=OrchestrationOperationsResponse)
def get_orchestration_operations(
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationOperationsResponse:
    return _projection_response(
        container,
        module="orchestration",
        response_cls=OrchestrationOperationsResponse,
    )


@router.get(
    "/orchestration/overview",
    response_model=OperationsModuleOverviewResponse,
)
def get_orchestration_operations_overview(
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsModuleOverviewResponse:
    return _projection_overview_response(container, "orchestration")


@router.get("/tool", response_model=ToolOperationsResponse)
def get_tool_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    time_window: str = Query(default="all"),
    search: str = Query(default=""),
    tool_id: str = Query(default="all"),
    provider: str = Query(default="all"),
    mode: str = Query(default="all"),
    strategy: str = Query(default="all"),
    environment: str = Query(default="all"),
    worker_id: str = Query(default="all"),
    has_artifact: str = Query(default="all"),
    retryable: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ToolOperationsResponse:
    return _projection_response(
        container,
        module="tool",
        response_cls=ToolOperationsResponse,
        table="tool_runs",
        filters={
            "status": status,
            "time_window": time_window,
            "search": search,
            "tool_id": tool_id,
            "provider": provider,
            "mode": mode,
            "strategy": strategy,
            "environment": environment,
            "worker_id": worker_id,
            "has_artifact": has_artifact,
            "retryable": retryable,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/llm", response_model=LlmOperationsResponse)
def get_llm_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    time_window: str = Query(default="all"),
    search: str = Query(default=""),
    llm_id: str = Query(default="all"),
    provider: str = Query(default="all"),
    streaming: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> LlmOperationsResponse:
    return _projection_response(
        container,
        module="llm",
        response_cls=LlmOperationsResponse,
        table="recent_invocations",
        filters={
            "status": status,
            "time_window": time_window,
            "search": search,
            "llm_id": llm_id,
            "provider": provider,
            "streaming": streaming,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get(
    "/tool/runs/{run_id}/detail",
    response_model=ToolRunDetailResponse,
)
def get_tool_run_operations_detail(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolRunDetailResponse:
    return ToolRunDetailResponse(
        **_detail_projection_payload(
            container,
            module="tool",
            kind="tool_run_detail",
            query_key=run_id,
        ),
    )


@router.get(
    "/llm/invocations/{invocation_id}/detail",
    response_model=LlmInvocationDetailResponse,
)
def get_llm_invocation_operations_detail(
    invocation_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmInvocationDetailResponse:
    return LlmInvocationDetailResponse(
        **_detail_projection_payload(
            container,
            module="llm",
            kind="llm_invocation_detail",
            query_key=invocation_id,
        ),
    )


@router.get("/memory", response_model=MemoryOperationsResponse)
def get_memory_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    agent_id: str = Query(default=""),
    kind: str = Query(default="all"),
    search: str = Query(default=""),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MemoryOperationsResponse:
    return _projection_response(
        container,
        module="memory",
        response_cls=MemoryOperationsResponse,
        table="source_files",
        filters={
            "agent_id": agent_id,
            "kind": kind,
            "search": search,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/skills", response_model=SkillsOperationsResponse)
def get_skills_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    surface: str = Query(default="interactive"),
    source: str = Query(default="all"),
    status: str = Query(default="all"),
    search: str = Query(default=""),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SkillsOperationsResponse:
    return _projection_response(
        container,
        module="skills",
        response_cls=SkillsOperationsResponse,
        table="recently_resolved_skills",
        filters={
            "surface": surface,
            "source": source,
            "status": status,
            "search": search,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/access", response_model=AccessOperationsResponse)
def get_access_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    kind: str = Query(default="all"),
    usage_type: str = Query(default="all"),
    search: str = Query(default=""),
    include_ready: bool = Query(default=True),
    include_disabled: bool = Query(default=False),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AccessOperationsResponse:
    return _projection_response(
        container,
        module="access",
        response_cls=AccessOperationsResponse,
        table="access_targets",
        filters={
            "status": status,
            "kind": kind,
            "usage_type": usage_type,
            "search": search,
            "include_ready": include_ready,
            "include_disabled": include_disabled,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/channels", response_model=ChannelsOperationsResponse)
def get_channels_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    channel_type: str = Query(default="all"),
    search: str = Query(default=""),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ChannelsOperationsResponse:
    return _projection_response(
        container,
        module="channels",
        response_cls=ChannelsOperationsResponse,
        table="channel_status",
        filters={
            "status": status,
            "channel_type": channel_type,
            "search": search,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/events", response_model=EventsOperationsResponse)
def get_events_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    topic_prefix: str = Query(default=""),
    search: str = Query(default=""),
    owner: str = Query(default="all"),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EventsOperationsResponse:
    return _projection_response(
        container,
        module="events",
        response_cls=EventsOperationsResponse,
        table="recent_events",
        filters={
            "status": status,
            "topic_prefix": topic_prefix,
            "search": search,
            "owner": owner,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/daemon", response_model=DaemonOperationsResponse)
def get_daemon_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    status: str = Query(default="all"),
    service_key: str = Query(default="all"),
    service_group: str = Query(default="all"),
    search: str = Query(default=""),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DaemonOperationsResponse:
    return _projection_response(
        container,
        module="daemon",
        response_cls=DaemonOperationsResponse,
        table="services",
        filters={
            "status": status,
            "service_key": service_key,
            "service_group": service_group,
            "search": search,
            "limit": limit,
            "offset": offset,
        },
    )


@router.post(
    "/orchestration/runs/{run_id}/cancel",
    response_model=dict[str, Any],
)
def cancel_orchestration_run_from_operations(
    run_id: str,
    request: OperationsActionReasonRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="orchestration.run.cancel",
        target_type="orchestration_run",
        target_id=run_id,
        target={"run_id": run_id},
        default_reason="Operations orchestration run cancellation",
    )
    try:
        run = _operations_action_service(container).cancel_orchestration_run(
            run_id=run_id,
            reason=reason,
        )
    except OrchestrationRunNotFoundError as exc:
        http_exc = HTTPException(status_code=404, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except OrchestrationValidationError as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = _orchestration_run_action_payload(run)
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload


@router.post(
    "/orchestration/runs/{run_id}/resume",
    response_model=dict[str, Any],
)
def resume_orchestration_run_from_operations(
    run_id: str,
    request: OperationsActionReasonRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OrchestrationRunResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="orchestration.run.resume",
        target_type="orchestration_run",
        target_id=run_id,
        target={"run_id": run_id},
        default_reason="Operations orchestration run resume",
    )
    try:
        run = _operations_action_service(container).resume_orchestration_run(
            run_id=run_id,
            reason=reason,
        )
    except OrchestrationRunNotFoundError as exc:
        http_exc = HTTPException(status_code=404, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except OrchestrationValidationError as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = _orchestration_run_action_payload(run)
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload


@router.post(
    "/tool/runs/{run_id}/cancel",
    response_model=OperationsToolRunActionResponse,
)
def cancel_tool_run_from_operations(
    run_id: str,
    request: OperationsActionReasonRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsToolRunActionResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="tool.run.cancel",
        target_type="tool_run",
        target_id=run_id,
        target={"run_id": run_id},
        default_reason="Operations tool run cancellation",
    )
    try:
        run = _operations_action_service(container).cancel_tool_run(
            run_id=run_id,
            reason=reason,
        )
    except ToolRunNotFoundError as exc:
        http_exc = HTTPException(status_code=404, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = _tool_run_action_response(run)
    _mark_operations_action_succeeded(container, audit_id, response)
    return response


@router.post(
    "/tool/runs/{run_id}/retry",
    response_model=OperationsToolRunActionResponse,
)
async def retry_tool_run_from_operations(
    run_id: str,
    request: OperationsActionReasonRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsToolRunActionResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="tool.run.retry",
        target_type="tool_run",
        target_id=run_id,
        target={"run_id": run_id},
        default_reason="Operations tool run retry",
    )
    try:
        original = container.tool_service.get_tool_run(run_id)
        authorize_tool_run(
            container,
            tool_id=original.tool_id,
            mode=original.target.mode,
            strategy=original.target.strategy,
            environment=original.target.environment,
            interface_name="http",
        )
        run = await _operations_action_service(container).retry_tool_run(
            run_id=run_id,
            reason=reason,
        )
    except ToolRunNotFoundError as exc:
        http_exc = HTTPException(status_code=404, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except ToolValidationError as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from None
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = _tool_run_action_response(run)
    _mark_operations_action_succeeded(container, audit_id, response)
    return response


@router.post(
    "/tool/workers/prune-expired",
    response_model=OperationsToolWorkerPruneResponse,
)
def prune_expired_tool_workers_from_operations(
    request: OperationsToolWorkerPruneRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsToolWorkerPruneResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="tool.workers.prune_expired",
        target_type="tool_workers",
        target={"retention_seconds": request.retention_seconds},
        default_reason="Operations prune expired tool workers",
    )
    try:
        result = _operations_action_service(container).prune_expired_tool_workers(
            retention_seconds=request.retention_seconds,
            reason=reason,
        )
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = OperationsToolWorkerPruneResponse(
        pruned_count=int(result["pruned_count"]),
        worker_ids=[str(item) for item in result["worker_ids"]],
        cutoff=format_datetime_utc(result["cutoff"]),
    )
    _mark_operations_action_succeeded(container, audit_id, response)
    return response


@router.post(
    "/channels/dead-letters/{channel_type}/replay",
    response_model=dict[str, Any],
)
def replay_channel_dead_letter_from_operations(
    channel_type: str,
    request: OperationsChannelDeadLetterReplayRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelDeadLetterReplayResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="channels.dead_letter.replay",
        target_type="channel_dead_letter",
        target_id=request.event_id or request.cursor,
        target={
            "channel_type": channel_type,
            "runtime_id": request.runtime_id,
            "cursor": request.cursor,
            "event_id": request.event_id,
        },
        default_reason="Operations channel dead-letter replay",
    )
    try:
        result = _operations_action_service(container).replay_channel_dead_letter(
            channel_type=channel_type,
            runtime_id=request.runtime_id,
            cursor=request.cursor,
            event_id=request.event_id,
            reason=reason,
        )
    except LookupError as exc:
        http_exc = HTTPException(status_code=404, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from exc
    except ValueError as exc:
        status_code = 409 if channel_type.strip().lower() != "webhook" else 400
        http_exc = HTTPException(status_code=status_code, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from exc
    except RuntimeError as exc:
        http_exc = HTTPException(status_code=502, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from exc
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = {
        "replayed": bool(result["replayed"]),
        "dead_letter_topic": str(result["dead_letter_topic"]),
        "dead_letter_cursor": str(result["dead_letter_cursor"]),
        "dead_letter_event_id": str(result["dead_letter_event_id"]),
        "outbound_id": str(result["outbound_id"]),
        "replay_mode": str(result["replay_mode"]),
        "callback_status": (
            str(result["callback_status"])
            if result.get("callback_status") is not None
            else None
        ),
    }
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload


@router.post("/skills/validate", response_model=dict[str, Any])
def validate_skill_package_from_operations(
    request: OperationsSkillValidateRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="skills.package.validate",
        target_type="skill_package",
        target_id=request.path,
        target={"path": request.path},
        default_reason="Operations skill package validation",
    )
    try:
        package = _operations_action_service(container).validate_skill_package(
            path=request.path,
            reason=reason,
        )
    except SkillError as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from exc
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = _skill_package_payload(package)
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload


@router.post("/skills/install", response_model=dict[str, Any])
def install_global_skill_from_operations(
    request: OperationsSkillInstallRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillInstallResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="skills.global.install",
        target_type="skill_package",
        target_id=request.source_dir,
        target={"source_dir": request.source_dir},
        default_reason="Operations global skill install",
    )
    try:
        result = _operations_action_service(container).install_global_skill(
            source_dir=request.source_dir,
            reason=reason,
        )
    except SkillError as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from exc
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = {
        "scope": result.scope.value,
        "target_root": result.target_root,
        "target_path": result.target_path,
        "skill": _skill_package_payload(result.package),
    }
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload


@router.get("/access/inventory", response_model=dict[str, Any])
def get_access_inventory_from_operations(
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
    include_ready: bool = Query(default=True),
    include_disabled: bool = Query(default=False),
) -> AccessInventoryResponse:
    payload = _operations_action_service(container).collect_access_inventory(
        workspace_dir=workspace_dir,
        include_ready=include_ready,
        include_disabled=include_disabled,
    )
    return payload


@router.post("/access/check", response_model=dict[str, Any])
def check_access_from_operations(
    request: OperationsAccessCheckRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AccessCheckResponse:
    _reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="access.readiness.check",
        target_type="access_readiness",
        target={
            "requirements": request.requirements,
            "credential_bindings": request.credential_bindings,
            "workspace_dir": request.workspace_dir,
        },
        default_reason="Operations access readiness check",
    )
    try:
        readiness_items = _operations_action_service(container).check_access_readiness(
            requirements=request.requirements,
            credential_bindings=request.credential_bindings,
            workspace_dir=request.workspace_dir,
            allow_literal_credentials=request.allow_literal_credentials,
        )
        checks = [
            present_readiness(readiness, target_type=target_type)
            for target_type, readiness in readiness_items
        ]
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = {
        "ready": all(bool(check["ready"]) for check in checks),
        "checks": checks,
    }
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload


@router.get("/access/setup", response_model=dict[str, Any])
def get_access_setup_from_operations(
    target: Annotated[str, Query(...)],
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
) -> AccessSetupFlowResponse:
    flow = _operations_action_service(container).begin_access_setup(
        target=target,
        workspace_dir=workspace_dir,
    )
    return present_setup_flow(flow)


@router.post(
    "/daemon/services/{service_key}/{action}",
    response_model=list[dict[str, Any]],
)
def run_daemon_service_action_from_operations(
    service_key: str,
    action: str,
    request: OperationsDaemonServiceActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[dict[str, Any]]:
    normalized_action = action.strip().lower()
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type=f"daemon.service.{normalized_action}",
        target_type="daemon_service",
        target_id=service_key,
        target={"service_key": service_key, "action": normalized_action},
        default_reason=f"Operations daemon action {normalized_action} for {service_key}",
        dangerous=normalized_action == "stop",
    )
    try:
        instances = _operations_action_service(container).run_daemon_service_action(
            service_key=service_key,
            action=action,
            reason=reason,
        )
    except (DaemonValidationError, DaemonNotFoundError, ValueError) as exc:
        http_exc = HTTPException(status_code=400, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from exc
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    payload = [instance_payload(instance) for instance in instances]
    _mark_operations_action_succeeded(container, audit_id, payload)
    return payload


@router.post(
    "/memory/long-term",
    response_model=OperationsMemoryWriteResultResponse,
)
def write_long_term_memory_from_operations(
    request: OperationsMemoryWriteLongTermRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsMemoryWriteResultResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="memory.long_term.write",
        target_type="agent_memory",
        target_id=request.agent_id,
        target={"agent_id": request.agent_id},
        default_reason="Operations long-term memory write",
    )
    try:
        result = _operations_action_service(container).write_long_term_memory(
            agent_id=request.agent_id,
            content=request.content,
            reason=reason,
        )
    except LookupError as exc:
        http_exc = HTTPException(status_code=404, detail=str(exc))
        _mark_operations_action_failed(container, audit_id, http_exc)
        raise http_exc from exc
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = OperationsMemoryWriteResultResponse(
        path=result.path,
        line_start=result.line_start,
        line_end=result.line_end,
        kind=result.kind,
    )
    _mark_operations_action_succeeded(container, audit_id, response)
    return response


@router.get(
    "/actions/audits",
    response_model=list[OperationsActionAuditResponse],
)
def list_operations_action_audits(
    container: Annotated[AppContainer, Depends(get_container)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[OperationsActionAuditResponse]:
    return [
        OperationsActionAuditResponse.from_value(audit)
        for audit in container.operations_action_audit_store.list_recent(
            limit=limit,
            offset=offset,
        )
    ]


@router.get("/{module}", response_model=OperationsModulePageResponse)
def get_operations_module(
    module: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsModulePageResponse:
    return _projection_response(
        container,
        module=module,
        response_cls=OperationsModulePageResponse,
        kind="module_page",
    )


@router.get("/{module}/overview", response_model=OperationsModuleOverviewResponse)
def get_operations_module_overview(
    module: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsModuleOverviewResponse:
    return _projection_overview_response(container, module)


def _projection_overview_response(
    container: AppContainer,
    module: str,
) -> OperationsModuleOverviewResponse:
    return _projection_response(
        container,
        module=module,
        kind="overview",
        response_cls=OperationsModuleOverviewResponse,
    )


def _projection_response(
    container: AppContainer,
    *,
    module: str,
    response_cls: type[Any],
    kind: str = "page",
    table: str | None = None,
    filters: dict[str, Any] | None = None,
) -> Any:
    payload = _projection_payload(container, module=module, kind=kind)
    if table is not None and filters is not None:
        _replace_table_from_projection(
            container,
            payload,
            module=module,
            table=table,
        )
        _apply_table_projection_filters(payload, table=table, filters=filters)
        _apply_related_projection_filters(
            payload,
            module=module,
            primary_table=table,
            filters=filters,
        )
    _strip_deferred_detail_payloads(payload, module=module, kind=kind)
    return response_cls(**payload)


def _replace_table_from_projection(
    container: AppContainer,
    payload: dict[str, Any],
    *,
    module: str,
    table: str,
) -> None:
    projection = container.operations_projection_store.get_projection(
        module=module.strip().lower(),
        kind="table",
        query_key=table,
    )
    if projection is None:
        return
    table_payload = deepcopy(projection.payload)
    if isinstance(table_payload, dict):
        payload[table] = table_payload


def _projection_payload(
    container: AppContainer,
    *,
    module: str,
    kind: str,
) -> dict[str, Any]:
    normalized_module = module.strip().lower()
    if normalized_module not in _PROJECTED_MODULES:
        raise HTTPException(
            status_code=404,
            detail=f"Operations projection for module '{module}' is not available.",
        )
    projection = container.operations_projection_store.get_projection(
        module=normalized_module,
        kind=kind,
    )
    if projection is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Operations projection is not materialized yet. "
                "Start or run the operations-observer worker."
            ),
        )
    return deepcopy(projection.payload)


def _detail_projection_payload(
    container: AppContainer,
    *,
    module: str,
    kind: str,
    query_key: str,
) -> dict[str, Any]:
    normalized_module = module.strip().lower()
    projection = container.operations_projection_store.get_projection(
        module=normalized_module,
        kind=kind,
        query_key=query_key,
    )
    if projection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Operations detail '{query_key}' is not available.",
        )
    return deepcopy(projection.payload)


def _strip_deferred_detail_payloads(
    payload: dict[str, Any],
    *,
    module: str,
    kind: str,
) -> None:
    if kind != "page":
        return
    normalized_module = module.strip().lower()
    if normalized_module == "tool":
        defer_tool_run_details_payload(payload)
    elif normalized_module == "llm":
        defer_llm_invocation_details_payload(payload)


def _apply_table_projection_filters(
    payload: dict[str, Any],
    *,
    table: str,
    filters: dict[str, Any],
) -> None:
    section = payload.get(table)
    if not isinstance(section, dict):
        return
    rows = tuple(row for row in section.get("rows", ()) if isinstance(row, dict))
    filtered_rows = [
        row
        for row in rows
        if _row_matches_status(
            row,
            str(filters.get("status") or "all"),
            table=table,
        )
        and _row_matches_search(row, str(filters.get("search") or ""))
        and _row_matches_exact_filters(row, filters)
    ]
    offset = max(_int_filter(filters.get("offset")), 0)
    limit = max(_int_filter(filters.get("limit"), default=len(filtered_rows)), 1)
    section["total"] = len(filtered_rows)
    section["rows"] = filtered_rows[offset : offset + limit]


def _apply_related_projection_filters(
    payload: dict[str, Any],
    *,
    module: str,
    primary_table: str,
    filters: dict[str, Any],
) -> None:
    if module != "access":
        return
    for table in (
        "missing_access",
        "provider_auth_blocked",
        "authentication_status",
        "access_usage",
        "setup_flows",
        "expiring_soon",
        "fallback_problems",
    ):
        if table == primary_table:
            continue
        _apply_table_projection_filters(payload, table=table, filters=filters)


def _row_matches_status(
    row: dict[str, Any],
    status: str,
    *,
    table: str,
) -> bool:
    normalized = status.strip().lower()
    if not normalized or normalized == "all":
        return True
    row_status = str(row.get("status") or "").strip().lower()
    cells = row.get("cells")
    if isinstance(cells, dict):
        row_status = row_status or str(cells.get("status") or "").strip().lower()
    if table == "tool_runs":
        if normalized == "waiting":
            return row_status in _TOOL_WAITING_STATUSES
        if normalized == "long_running":
            duration = (
                _duration_text_seconds(str(cells.get("duration") or ""))
                if isinstance(cells, dict)
                else 0
            )
            return (
                row_status in _TOOL_ACTIVE_STATUSES
                and duration >= _TOOL_LONG_RUNNING_SECONDS
            )
    if normalized == "active":
        return row_status in {"active", "running", "queued", "waiting", "processing"}
    if normalized == "failed":
        return row_status in {"failed", "timed_out", "timeout", "error"}
    return row_status == normalized


def _duration_text_seconds(value: str) -> int:
    total = 0.0
    for part in value.strip().lower().split():
        if part.endswith("ms"):
            total += _float_text(part.removesuffix("ms")) / 1000
        elif part.endswith("s"):
            total += _float_text(part.removesuffix("s"))
        elif part.endswith("m"):
            total += _float_text(part.removesuffix("m")) * 60
        elif part.endswith("h"):
            total += _float_text(part.removesuffix("h")) * 3600
    return int(round(total))


def _float_text(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def _row_matches_search(row: dict[str, Any], search: str) -> bool:
    needle = search.strip().lower()
    if not needle:
        return True
    return needle in _row_text(row)


def _row_matches_exact_filters(
    row: dict[str, Any],
    filters: dict[str, Any],
) -> bool:
    ignored = {
        "status",
        "search",
        "limit",
        "offset",
        "time_window",
        "include_ready",
        "include_disabled",
        "surface",
    }
    row_text = _row_text(row)
    cells = row.get("cells")
    for key, value in filters.items():
        if key in ignored:
            continue
        if value is None or isinstance(value, bool):
            continue
        normalized = str(value).strip().lower()
        if not normalized or normalized == "all":
            continue
        if isinstance(cells, dict) and key in cells:
            if str(cells.get(key) or "").strip().lower() != normalized:
                return False
            continue
        if normalized not in row_text:
            return False
    return True


def _row_text(row: dict[str, Any]) -> str:
    cells = row.get("cells")
    parts = [str(row.get("id") or ""), str(row.get("status") or "")]
    if isinstance(cells, dict):
        parts.extend(str(value) for value in cells.values())
    return " ".join(parts).lower()


def _int_filter(value: Any, *, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _runtime_status(container: AppContainer) -> OperationsRuntimeStatusResponse:
    database, migration = _database_runtime_status(container)
    events = _events_runtime_status(container)
    return OperationsRuntimeStatusResponse(
        updated_at=datetime.now(timezone.utc).isoformat(),
        checks=[database, events, migration],
    )


def _operations_stream_record_payload(record: EventTopicRecord) -> dict[str, Any]:
    payload = dict(record.envelope.payload)
    modules = _operations_stream_modules(payload)
    return {
        "event_type": "projection_updated",
        "event_id": record.envelope.id,
        "module": modules[0] if len(modules) == 1 else None,
        "modules": modules,
        "kinds": _operations_stream_kinds(payload),
        "query_key": str(payload.get("query_key") or "default"),
        "updated_at": str(
            payload.get("updated_at")
            or format_datetime_utc(record.envelope.occurred_at),
        ),
    }


def _operations_stream_modules(payload: dict[str, Any]) -> list[str]:
    candidates = [
        payload.get("module"),
        payload.get("module_id"),
        *(payload.get("modules") if isinstance(payload.get("modules"), list) else []),
    ]
    modules = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        module = candidate.strip().lower()
        if module in _PROJECTED_MODULES and module not in modules:
            modules.append(module)
    return modules


def _operations_stream_kinds(payload: dict[str, Any]) -> list[str]:
    raw_kinds = payload.get("kinds")
    if not isinstance(raw_kinds, list):
        raw_kinds = [payload.get("kind")]
    return [
        kind
        for item in raw_kinds
        if isinstance(item, str) and (kind := item.strip().lower())
    ]


def _format_operations_sse_event(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post(
    "/events/subscriptions/advance-to-head",
    response_model=OperationsEventSubscriptionAdvanceResponse,
)
def advance_event_subscriptions_to_head(
    request: OperationsEventSubscriptionAdvanceRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsEventSubscriptionAdvanceResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="events.subscriptions.advance_to_head",
        target_type="event_subscription",
        target_id=request.subscription_id,
        target={
            "subscription_id": request.subscription_id,
            "source_topic": request.source_topic,
            "status": request.status,
            "observer_only": request.observer_only,
            "dry_run": request.dry_run,
        },
        default_reason="Operations event subscription cursor advance",
        dangerous=not request.dry_run,
    )
    try:
        result = _operations_action_service(container).advance_event_subscriptions_to_head(
            subscription_id=request.subscription_id,
            source_topic=request.source_topic,
            status=request.status,
            observer_only=request.observer_only,
            dry_run=request.dry_run,
            reason=reason,
        )
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = OperationsEventSubscriptionAdvanceResponse.from_result(result)
    _mark_operations_action_succeeded(container, audit_id, response)
    return response


@router.post(
    "/events/observers/advance-to-head",
    response_model=OperationsEventSubscriptionAdvanceResponse,
)
def advance_event_observers_to_head(
    request: OperationsEventSubscriptionAdvanceRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsEventSubscriptionAdvanceResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="events.observers.advance_to_head",
        target_type="event_subscription",
        target_id=request.subscription_id,
        target={
            "subscription_id": request.subscription_id,
            "source_topic": request.source_topic,
            "status": request.status,
            "observer_only": True,
            "dry_run": request.dry_run,
        },
        default_reason="Operations observer cursor advance",
        dangerous=not request.dry_run,
    )
    try:
        result = _operations_action_service(container).advance_event_subscriptions_to_head(
            subscription_id=request.subscription_id,
            source_topic=request.source_topic,
            status=request.status,
            observer_only=True,
            dry_run=request.dry_run,
            reason=reason,
        )
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = OperationsEventSubscriptionAdvanceResponse.from_result(result)
    _mark_operations_action_succeeded(container, audit_id, response)
    return response


@router.post(
    "/channels/runtimes/prune-stale",
    response_model=OperationsChannelRuntimePruneResponse,
)
def prune_stale_channel_runtimes(
    request: OperationsChannelRuntimePruneRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsChannelRuntimePruneResponse:
    reason, audit_id = _begin_operations_action_audit(
        container,
        request,
        action_type="channels.runtimes.prune_stale",
        target_type="channel_runtime",
        target_id=request.runtime_id,
        target={
            "runtime_id": request.runtime_id,
            "channel_type": request.channel_type,
            "stale_after_seconds": request.stale_after_seconds,
            "dry_run": request.dry_run,
        },
        default_reason="Operations stale channel runtime prune",
        dangerous=not request.dry_run,
    )
    try:
        result = _operations_action_service(container).prune_stale_channel_runtimes(
            runtime_id=request.runtime_id,
            channel_type=request.channel_type,
            stale_after_seconds=request.stale_after_seconds,
            dry_run=request.dry_run,
            reason=reason,
        )
    except Exception as exc:
        _mark_operations_action_failed(container, audit_id, exc)
        raise
    response = OperationsChannelRuntimePruneResponse.from_result(result)
    _mark_operations_action_succeeded(container, audit_id, response)
    return response


def _database_runtime_status(
    container: AppContainer,
) -> tuple[OperationsRuntimeStatusItemResponse, OperationsRuntimeStatusItemResponse]:
    settings = container.settings
    url = settings.database_url
    database_value = _database_label(url)
    database_details = _safe_url(url)
    migration_value = "unknown"
    migration_status = "unknown"
    migration_tone = "warning"
    try:
        with container.engine.connect() as connection:
            dialect = connection.dialect.name
            driver = connection.dialect.driver
            connection.execute(text("select 1"))
            try:
                version = connection.execute(
                    text("select version_num from alembic_version"),
                ).scalar_one_or_none()
            except SQLAlchemyError:
                version = None
            migration_value = str(version or "uninitialized")
            migration_status = "current" if version else "uninitialized"
            migration_tone = "success" if version else "warning"
    except SQLAlchemyError as exc:
        return (
            OperationsRuntimeStatusItemResponse(
                id="database",
                label="Database",
                value=database_value,
                status="unreachable",
                tone="danger",
                details=f"{database_details}; {exc}",
            ),
            OperationsRuntimeStatusItemResponse(
                id="migration",
                label="Migration",
                value="unknown",
                status="unknown",
                tone="danger",
                details="Database is unreachable.",
            ),
        )

    if url.startswith("sqlite"):
        database_status = "sqlite"
        database_tone = "warning"
    else:
        database_status = "connected"
        database_tone = "success"
    return (
        OperationsRuntimeStatusItemResponse(
            id="database",
            label="Database",
            value=database_value,
            status=database_status,
            tone=database_tone,
            details=f"{database_details}; dialect={dialect}; driver={driver}",
        ),
        OperationsRuntimeStatusItemResponse(
            id="migration",
            label="Migration",
            value=migration_value,
            status=migration_status,
            tone=migration_tone,
            details="alembic_version",
        ),
    )


def _events_runtime_status(container: AppContainer) -> OperationsRuntimeStatusItemResponse:
    settings = container.settings
    if settings.events_backend != "redis":
        return OperationsRuntimeStatusItemResponse(
            id="events",
            label="Events",
            value=settings.events_backend,
            status="file",
            tone="warning",
            details=settings.events_state_dir,
        )
    url = settings.events_redis_url or ""
    try:
        from redis import Redis
        from redis.exceptions import RedisError

        client = Redis.from_url(url, decode_responses=True)
        client.ping()
    except (ImportError, RedisError, ValueError) as exc:
        return OperationsRuntimeStatusItemResponse(
            id="events",
            label="Events",
            value="redis",
            status="unreachable",
            tone="danger",
            details=f"{_safe_url(url)}; {exc}",
        )
    return OperationsRuntimeStatusItemResponse(
        id="events",
        label="Events",
        value="redis",
        status="connected",
        tone="success",
        details=f"{_safe_url(url)}; prefix={settings.events_redis_key_prefix}",
    )


def _operation_reason(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _validated_operations_action(
    request: OperationsActionRequest,
    *,
    default_reason: str,
    dangerous: bool = False,
    reason_required: bool = False,
) -> str:
    reason = _operation_reason(request.reason) or _operation_reason(default_reason)
    if (dangerous or reason_required) and _operation_reason(request.reason) is None:
        raise HTTPException(
            status_code=400,
            detail="reason is required for this operations action.",
        )
    if dangerous:
        if not _operation_confirmation(request.confirmation):
            raise HTTPException(
                status_code=400,
                detail="confirmation is required for this operations action.",
            )
        if not request.acknowledged_risk():
            raise HTTPException(
                status_code=400,
                detail="risk acknowledgement is required for this operations action.",
            )
    if reason is None:
        raise HTTPException(
            status_code=400,
            detail="reason is required for this operations action.",
        )
    return reason


def _begin_operations_action_audit(
    container: AppContainer,
    request: OperationsActionRequest,
    *,
    action_type: str,
    target_type: str,
    target_id: str | None = None,
    target: dict[str, Any] | None = None,
    default_reason: str,
    dangerous: bool = False,
    reason_required: bool = False,
) -> tuple[str, str]:
    reason = _validated_operations_action(
        request,
        default_reason=default_reason,
        dangerous=dangerous,
        reason_required=reason_required,
    )
    payload = _operations_action_audit_payload(
        request,
        reason=reason,
        dangerous=dangerous,
    )
    audit = container.operations_action_audit_store.record_attempt(
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        target=target or {},
        reason=reason,
        dangerous=bool(payload["dangerous"]),
        risk=str(payload["risk"]),
        confirmation=bool(payload["confirmation"]),
        risk_acknowledged=bool(payload["risk_acknowledged"]),
        operator=payload["operator"],
        source=str(payload["source"]),
        metadata=payload["metadata"],
    )
    return reason, audit.audit_id


def _mark_operations_action_succeeded(
    container: AppContainer,
    audit_id: str,
    result: Any,
) -> None:
    container.operations_action_audit_store.mark_succeeded(
        audit_id,
        result=_operation_result_summary(result),
    )


def _mark_operations_action_failed(
    container: AppContainer,
    audit_id: str,
    exc: BaseException,
) -> None:
    container.operations_action_audit_store.mark_failed(
        audit_id,
        error=_operation_error_summary(exc),
    )


def _operation_confirmation(value: bool | str | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    return False


def _operations_action_audit_payload(
    request: OperationsActionRequest,
    *,
    reason: str,
    dangerous: bool,
) -> dict[str, Any]:
    audit = request.audit
    metadata: dict[str, Any] = {}
    if audit is not None:
        metadata.update(dict(audit.metadata or {}))
    metadata.update(dict(request.metadata or {}))
    return {
        "reason": reason,
        "operator": (
            _operation_reason(request.operator)
            or _operation_reason(getattr(audit, "operator", None))
        ),
        "source": (
            _operation_reason(request.source)
            or _operation_reason(getattr(audit, "source", None))
            or "operations"
        ),
        "risk_acknowledged": request.acknowledged_risk(),
        "confirmation": _operation_confirmation(request.confirmation),
        "dangerous": dangerous,
        "risk": "dangerous" if dangerous else "normal",
        "metadata": metadata,
    }


def _operation_result_summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value.dict()
    if isinstance(value, dict):
        return _json_safe_summary(value)
    if isinstance(value, list):
        return {"items": _json_safe_summary(value), "count": len(value)}
    return {
        "type": type(value).__name__,
        "id": str(getattr(value, "id", "") or getattr(value, "run_id", "") or ""),
        "status": str(getattr(value, "status", "") or ""),
    }


def _operation_error_summary(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, HTTPException):
        return {
            "type": type(exc).__name__,
            "status_code": exc.status_code,
            "detail": _json_safe_summary(exc.detail),
        }
    return {
        "type": type(exc).__name__,
        "message": str(exc),
    }


def _json_safe_summary(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _json_safe_summary(item)
            for key, item in list(value.items())[:50]
        }
    if isinstance(value, list):
        return [_json_safe_summary(item) for item in value[:50]]
    if isinstance(value, tuple):
        return [_json_safe_summary(item) for item in value[:50]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _tool_run_action_response(run: Any) -> OperationsToolRunActionResponse:
    return OperationsToolRunActionResponse(
        id=run.id,
        tool_id=run.tool_id,
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        cancel_requested_at=format_optional_datetime_utc(
            getattr(run, "cancel_requested_at", None),
        ),
    )


def _orchestration_run_action_payload(run: Any) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status.value if hasattr(run.status, "value") else str(run.status),
        "stage": run.stage.value if hasattr(run.stage, "value") else str(run.stage),
        "lane_key": getattr(run, "lane_key", None),
        "worker_id": getattr(run, "worker_id", None),
    }


def _skill_package_payload(package: Any) -> dict[str, Any]:
    return {
        "name": package.name,
        "description": package.description,
        "version": package.version,
        "source": package.source,
        "root_path": package.root_path,
    }


def _database_label(database_url: str) -> str:
    if database_url.startswith("postgresql"):
        return "PostgreSQL"
    if database_url.startswith("sqlite"):
        return "SQLite"
    try:
        return make_url(database_url).get_backend_name()
    except Exception:
        return database_url.split(":", 1)[0] or "unknown"


def _safe_url(url: str) -> str:
    if not url:
        return "-"
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return url
