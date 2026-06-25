from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.interfaces.http_models import (
    OperationsToolRunActionResponse,
)
from crxzipple.shared.time import format_optional_datetime_utc


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
