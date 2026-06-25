from __future__ import annotations

from crxzipple.modules.orchestration.domain import ExecutionStepItem, OrchestrationRun
from crxzipple.modules.workbench.application.projection_helpers import metadata_str


def execution_item_owner_id(
    item: ExecutionStepItem,
    *,
    owner_kind: str,
) -> str | None:
    if item.owner is None or item.owner.owner_kind != owner_kind:
        return None
    return item.owner.owner_id


def execution_item_summary(item: ExecutionStepItem | None) -> dict[str, object]:
    if item is None or not isinstance(item.summary_payload, dict):
        return {}
    return dict(item.summary_payload)


def summary_text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def summary_text_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list | tuple):
        return []
    values = [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]
    return list(dict.fromkeys(values))


def summary_bool(payload: dict[str, object], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def request_render_snapshot_id(
    run: OrchestrationRun,
    *,
    summary: dict[str, object],
) -> str | None:
    return (
        summary_text(summary, "request_render_snapshot_id")
        or metadata_str(run, "request_render_snapshot_id")
    )


def summary_text_from_items(
    items: tuple[ExecutionStepItem, ...],
    key: str,
) -> str | None:
    for item in items:
        value = summary_text(execution_item_summary(item), key)
        if value is not None:
            return value
    return None


def summary_dict_from_items(
    items: tuple[ExecutionStepItem, ...],
    key: str,
) -> dict[str, object]:
    for item in items:
        value = execution_item_summary(item).get(key)
        if isinstance(value, dict):
            return dict(value)
    return {}
