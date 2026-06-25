from __future__ import annotations

from typing import Any

from crxzipple.modules.channels.application.payload_redaction import (
    redact_channel_payload,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    label_from_key,
    text,
    tone_for_status,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def table(
    section_id: str,
    title: str,
    columns: tuple[tuple[str, str], ...],
    rows: tuple[dict[str, Any], ...],
    *,
    total: int | None = None,
    empty_state: str,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id=section_id,
        title=title,
        columns=tuple(
            OperationsTableColumnModel(key=key, label=label)
            for key, label in columns
        ),
        rows=tuple(
            OperationsTableRowModel(
                id=row_id(section_id, index, row),
                cells={
                    key: text(value)
                    for key, value in row.items()
                    if not key.startswith("_") and key != "tone"
                },
                status=text(row.get("status"), "-"),
                tone=text(row.get("tone"), tone_for_status(text(row.get("status")))),
            )
            for index, row in enumerate(rows)
        ),
        total=len(rows) if total is None else total,
        view_all_route=f"/operations/channels?tab={section_id}",
        empty_state=empty_state,
    )


def row_id(section_id: str, index: int, row: dict[str, Any]) -> str:
    for key in (
        "id",
        "interaction_id",
        "runtime_id",
        "event_id",
        "connection_id",
        "account_id",
        "channel_type",
    ):
        value = text(row.get(key), "")
        if value:
            return value[:120]
    return f"{section_id}:{index}"


def overview_rows(section: OperationsTableSectionModel) -> tuple[dict[str, str], ...]:
    return tuple(dict(row.cells) for row in section.rows)


def key_value_section(
    section_id: str,
    title: str,
    values: dict[str, Any],
) -> OperationsKeyValueSectionModel:
    display_values = redact_channel_payload(values)
    return OperationsKeyValueSectionModel(
        id=section_id,
        title=title,
        items=tuple(
            OperationsKeyValueItemModel(
                label_from_key(key),
                text(value),
                tone_for_status(text(value), default="neutral"),
            )
            for key, value in display_values.items()
            if text(value, "") != ""
        ),
    )


def capabilities_section(capabilities: Any) -> OperationsKeyValueSectionModel:
    payload = capabilities_payload(capabilities)
    return OperationsKeyValueSectionModel(
        id="capabilities",
        title="Capabilities",
        items=tuple(
            OperationsKeyValueItemModel(
                label_from_key(key),
                text(value),
                "success" if bool(value) else "neutral",
            )
            for key, value in payload.items()
            if key != "metadata"
        ),
    )


def capabilities_label(capabilities: Any) -> str:
    payload = capabilities_payload(capabilities)
    enabled = [
        label_from_key(key)
        for key, value in payload.items()
        if key != "metadata" and bool(value)
    ]
    return ", ".join(enabled) if enabled else "-"


def capabilities_payload(capabilities: Any) -> dict[str, Any]:
    if capabilities is None:
        return {}
    to_payload = getattr(capabilities, "to_payload", None)
    if callable(to_payload):
        try:
            payload = to_payload()
            return dict(payload) if isinstance(payload, dict) else {}
        except Exception:
            return {}
    return {}
