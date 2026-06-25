from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.access_common import (
    kind_label,
    status_label,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.access_target_projection import (
    requirements_text,
    required_by,
    target_checks,
    target_label,
    target_metadata,
    target_worst_status,
)
from crxzipple.modules.operations.application.read_models.access_values import (
    bool_value,
    dict_value,
    text,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def access_requirements_table(
    targets: tuple[dict[str, Any], ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for target in targets:
        checks = target_checks(target)
        if not checks:
            rows.append(access_requirement_row(target, None, len(rows)))
            continue
        for check in checks:
            rows.append(access_requirement_row(target, check, len(rows)))
    return OperationsTableSectionModel(
        id="access_requirements",
        title="Credential Requirements",
        columns=(
            OperationsTableColumnModel("consumer", "Consumer"),
            OperationsTableColumnModel("module", "Module"),
            OperationsTableColumnModel("slot", "Slot"),
            OperationsTableColumnModel("expected_kind", "Expected Kind"),
            OperationsTableColumnModel("binding", "Binding"),
            OperationsTableColumnModel("readiness", "Readiness"),
            OperationsTableColumnModel("setup", "Setup"),
            OperationsTableColumnModel("last_checked", "Last Checked"),
        ),
        rows=tuple(rows),
        total=max(total, len(rows)),
        empty_state="No credential requirements declared.",
    )


def access_requirement_row(
    target: dict[str, Any],
    check: dict[str, Any] | None,
    index: int,
) -> OperationsTableRowModel:
    status = target_worst_status(target) if check is None else text(
        check.get("status"),
        "unknown",
    )
    usages = target_metadata(target).get("usages")
    modules = sorted(
        {
            text(dict_value(usage).get("consumer_module"))
            for usage in (usages if isinstance(usages, list | tuple) else [])
            if text(dict_value(usage).get("consumer_module"))
        },
    )
    requirement = text(check.get("requirement")) if check else requirements_text(target)
    return OperationsTableRowModel(
        id=f"{text(target.get('resource_id'), '')}:requirement:{index}",
        cells={
            "consumer": required_by(target),
            "module": ", ".join(modules) or "-",
            "slot": requirement,
            "expected_kind": text(check.get("kind")) if check else kind_label(
                text(target_metadata(target).get("asset_kind")),
            ),
            "binding": text(check.get("binding_id") or check.get("credential_binding_id"))
            if check
            else target_label(target),
            "readiness": status_label(status),
            "setup": "Available"
            if (check and bool_value(check.get("setup_available")))
            or bool_value(target.get("setup_available"))
            else "-",
            "last_checked": text(check.get("observed_at")) if check else "-",
        },
        status=status_label(status),
        tone=tone_for_status(status),
    )
