from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.operations.interfaces.http_action_audit import (
    _begin_operations_action_audit,
    _mark_operations_action_failed,
    _mark_operations_action_succeeded,
)
from crxzipple.modules.operations.interfaces.http_action_service import (
    operations_action_service,
)
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsChannelDeadLetterReplayRequest,
    OperationsChannelRuntimePruneRequest,
    OperationsChannelRuntimePruneResponse,
)

router = APIRouter()


@router.post(
    "/channels/dead-letters/{channel_type}/replay",
    response_model=dict[str, Any],
)
def replay_channel_dead_letter_from_operations(
    channel_type: str,
    request: OperationsChannelDeadLetterReplayRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
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
        risk="dangerous",
    )
    try:
        result = operations_action_service(container).replay_channel_dead_letter(
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
        risk="dangerous" if not request.dry_run else "normal",
    )
    try:
        result = operations_action_service(container).prune_stale_channel_runtimes(
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
