from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.http.ui_models import (
    ConsoleSectionResponse,
    UiBootstrapResponse,
)
from crxzipple.shared.runtime_console import ConsoleSection


router = APIRouter()

@router.get("/bootstrap", response_model=UiBootstrapResponse)
def bootstrap(
    container: Annotated[AppContainer, Depends(get_container)],
) -> UiBootstrapResponse:
    sections = [
        ConsoleSection(
            id="workbench",
            owner="workbench",
            status="ready",
            updated_at=None,
            data={"preferred_refresh": "sse+query"},
        ),
        ConsoleSection(
            id="events",
            owner="events",
            status="ready" if container.require(AppKey.EVENTS_SERVICE) is not None else "degraded",
            updated_at=None,
            data={"stream_available": container.require(AppKey.EVENTS_SERVICE) is not None},
        ),
    ]
    return UiBootstrapResponse(
        version=1,
        app_name=container.require(AppKey.CORE_SETTINGS).app_name,
        environment=container.require(AppKey.CORE_SETTINGS).environment,
        routes=[
            "/ui/bootstrap",
            "/ui/access",
            "/ui/access/assets",
            "/ui/access/assets/{asset_id}",
            "/ui/access/policies",
            "/ui/access/consumers",
            "/authorization/policies",
            "/authorization/policies/{policy_id}",
            "/authorization/policies/{policy_id}/enable",
            "/authorization/policies/{policy_id}/disable",
            "/authorization/policies/import",
            "/authorization/policies/export",
            "/authorization/policies/dry-run",
            "/authorization/policies/impact",
            "/authorization/audits",
            "/ui/workbench/home",
            "/ui/workbench/turns",
            "/ui/workbench/turns/{run_id}/cancel",
            "/ui/workbench/turns/{run_id}/approvals/{request_id}",
            "/ui/workbench/runs/{run_id}",
            "/ui/workbench/runs/{run_id}/steps",
            "/ui/workbench/linked-entities/{entity_type}/{entity_id}",
            "/ui/workbench/context-tree/by-session/{session_key}",
            "/ui/workbench/context-tree/by-session/{session_key}/nodes/{node_id}/actions/{action}",
            "/ui/workbench/context-snapshots/runs/{run_id}",
            "/ui/workbench/context-snapshots/{snapshot_id}",
            "/ui/workbench/runs/{run_id}/llm-request-preview",
            "/ui/workbench/llm-invocations/{invocation_id}/llm-request-preview",
            "/workbench/traces/{trace_id}",
            "/operations/orchestration",
            "/operations/tool",
            "/operations/browser",
            "/operations/llm",
            "/operations/access",
            "/operations/channels",
            "/operations/memory",
            "/operations/skills",
            "/operations/events",
            "/operations/daemon",
            "/operations/runtime",
            "/operations/orchestration/overview",
            "/operations/tool/overview",
            "/operations/browser/overview",
            "/operations/llm/overview",
            "/operations/access/overview",
            "/operations/channels/overview",
            "/operations/memory/overview",
            "/operations/skills/overview",
            "/operations/events/overview",
            "/operations/daemon/overview",
            "/operations/{module}/overview",
            "/operations/events/subscriptions/advance-to-head",
            "/operations/events/observers/advance-to-head",
            "/operations/channels/runtimes/prune-stale",
            "/operations/channels/dead-letters/{channel_type}/replay",
            "/operations/memory/long-term",
            "/operations/llm/invocations/{invocation_id}/detail",
            "/operations/llm/profiles/{llm_id}/warmup",
            "/operations/orchestration/runs/{run_id}/cancel",
            "/operations/orchestration/runs/{run_id}/resume",
            "/operations/tool/runs/{run_id}/detail",
            "/operations/tool/runs/{run_id}/cancel",
            "/operations/tool/runs/{run_id}/retry",
            "/operations/tool/workers/prune-expired",
            "/operations/access/inventory",
            "/operations/access/check",
            "/operations/access/setup",
            "/operations/daemon/services/{service_key}/ensure",
            "/operations/daemon/services/{service_key}/healthcheck",
            "/operations/daemon/services/{service_key}/reconcile",
            "/operations/daemon/services/{service_key}/stop",
            "/operations/skills/validate",
            "/operations/skills/sync",
            "/operations/skills/install",
            "/turns",
            "/turns/{run_id}",
            "/turns/{run_id}/llm-request-preview",
            "/turns/{run_id}/compact",
            "/turns/{run_id}/heartbeat",
            "/turns/{run_id}/memory-flush",
            "/turns/{run_id}/approvals/{request_id}",
            "/ui/trace/{trace_id}",
            "/ui/trace/{trace_id}/events",
        ],
        sections=[ConsoleSectionResponse.from_value(item) for item in sections],
    )
