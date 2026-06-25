from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
)
from crxzipple.modules.operations.application.read_models.tool_worker_projection import (
    worker_capability_summary,
)
from crxzipple.modules.tool.domain import ToolWorkerRegistration


def tool_worker_capabilities_section(
    worker: ToolWorkerRegistration,
) -> OperationsKeyValueSectionModel:
    policy = worker.capabilities_payload.get("concurrency_policy")
    if not isinstance(policy, dict):
        policy = {}
    return OperationsKeyValueSectionModel(
        id="worker_capabilities",
        title="Worker Capabilities",
        items=(
            OperationsKeyValueItemModel(
                label="Max In Flight",
                value=str(worker.max_in_flight),
            ),
            OperationsKeyValueItemModel(
                label="Current In Flight",
                value=str(worker.current_in_flight),
            ),
            OperationsKeyValueItemModel(
                label="Default Max In Flight",
                value=_display(policy.get("default_max_in_flight")),
            ),
            OperationsKeyValueItemModel(
                label="Image Max In Flight",
                value=_display(policy.get("image_max_in_flight")),
            ),
            OperationsKeyValueItemModel(
                label="Shared State Max In Flight",
                value=_display(policy.get("shared_state_max_in_flight")),
            ),
            OperationsKeyValueItemModel(
                label="Capability Groups",
                value=worker_capability_summary(worker),
            ),
        ),
    )


def _display(value: object | None) -> str:
    return display_value(value)
