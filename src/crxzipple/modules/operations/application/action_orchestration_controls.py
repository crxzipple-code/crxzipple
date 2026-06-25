from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.action_dependencies import (
    required_dependency,
)
from crxzipple.modules.orchestration.application.commands import (
    ResumeOrchestrationRunInput,
)


def cancel_orchestration_run(
    orchestration_cancellation_service: Any,
    *,
    run_id: str,
    reason: str | None = None,
) -> Any:
    return required_dependency(
        orchestration_cancellation_service,
        "orchestration cancellation service",
    ).cancel_run(run_id, reason=reason)


def resume_orchestration_run(
    orchestration_resume_service: Any,
    *,
    run_id: str,
    reason: str | None = None,
) -> Any:
    return required_dependency(
        orchestration_resume_service,
        "orchestration resume service",
    ).resume_run(
        ResumeOrchestrationRunInput(
            run_id=run_id,
            reason=reason,
        ),
    )
