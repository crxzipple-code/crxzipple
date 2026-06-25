from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.access_common import (
    kind_label,
    status_label,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.access_target_projection import (
    events_for_target,
    requirements_text,
    target_label,
    target_metadata,
    target_reason,
    target_worst_status,
)
from crxzipple.modules.operations.application.read_models.access_values import (
    bool_value,
    text,
)
from crxzipple.modules.operations.application.read_models.access_detail_tables import (
    checks_table,
    target_setup_table,
    target_usages_table,
)
from crxzipple.modules.operations.application.read_models.access_event_tables import (
    access_events_table,
)
from crxzipple.modules.operations.application.read_models.access_models import (
    AccessTargetDetailModel,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)


def target_details(
    targets: tuple[dict[str, Any], ...],
    *,
    observed_events: tuple[OperationsObservedEvent, ...],
) -> tuple[AccessTargetDetailModel, ...]:
    details: list[AccessTargetDetailModel] = []
    for target in targets[:80]:
        target_id = text(target.get("resource_id"), "")
        status = target_worst_status(target)
        target_events = events_for_target(observed_events, target)
        details.append(
            AccessTargetDetailModel(
                target_id=target_id,
                title=target_label(target),
                status=status_label(status),
                tone=tone_for_status(status),
                summary=(
                    OperationsKeyValueItemModel("Asset", target_label(target)),
                    OperationsKeyValueItemModel("Kind", kind_label(text(target_metadata(target).get("asset_kind")))),
                    OperationsKeyValueItemModel("Status", status_label(status), tone_for_status(status)),
                    OperationsKeyValueItemModel(
                        "Ready",
                        "Yes" if bool_value(target.get("ready")) else "No",
                        "success" if bool_value(target.get("ready")) else "warning",
                    ),
                    OperationsKeyValueItemModel(
                        "Setup Available",
                        "Yes" if bool_value(target.get("setup_available")) else "No",
                    ),
                    OperationsKeyValueItemModel("Usage Count", text(target_metadata(target).get("usage_count"))),
                    OperationsKeyValueItemModel("Requirements", requirements_text(target)),
                    OperationsKeyValueItemModel("Reason", target_reason(target)),
                ),
                checks=checks_table(target),
                usages=target_usages_table(target),
                setup=target_setup_table(target),
                events=access_events_table(target_events),
                raw_payload={
                    "target": dict(target),
                    "events": [
                        event.to_payload()
                        for event in target_events
                    ],
                },
            )
        )
    return tuple(details)
