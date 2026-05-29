"""normalize runtime defaults settings payloads

Revision ID: 0059_runtime_defaults_nested_schema
Revises: 0058_memory_policies
Create Date: 2026-05-22 00:00:00
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "0059_runtime_defaults_nested_schema"
down_revision = "0058_memory_policies"
branch_labels = None
depends_on = None


RUNTIME_DEFAULTS_KIND = "runtime-defaults"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("settings_resource_versions"):
        _normalize_json_table(
            bind,
            table_name="settings_resource_versions",
            id_column="version_id",
            payload_column="payload",
        )
    if inspector.has_table("settings_effective_snapshots"):
        _normalize_json_table(
            bind,
            table_name="settings_effective_snapshots",
            id_column="snapshot_id",
            payload_column="effective_payload",
        )
    if inspector.has_table("settings_overrides"):
        _normalize_json_table(
            bind,
            table_name="settings_overrides",
            id_column="override_id",
            payload_column="override_payload",
        )


def downgrade() -> None:
    # The nested schema is the current contract. Downgrade intentionally leaves
    # existing payloads intact instead of reintroducing removed flat keys.
    return None


def _normalize_json_table(
    bind: sa.Connection,
    *,
    table_name: str,
    id_column: str,
    payload_column: str,
) -> None:
    rows = bind.execute(
        sa.text(
            f"""
            SELECT {id_column}, resource_id, {payload_column}
            FROM {table_name}
            WHERE resource_kind = :resource_kind
            """,
        ),
        {"resource_kind": RUNTIME_DEFAULTS_KIND},
    ).mappings()

    for row in rows:
        payload = _decode_json_payload(row[payload_column])
        if not payload:
            continue
        normalized = _normalize_runtime_defaults_payload(
            row.get("resource_id"),
            payload,
        )
        if normalized == payload:
            continue
        _update_json_payload(
            bind,
            table_name=table_name,
            id_column=id_column,
            id_value=row[id_column],
            payload_column=payload_column,
            payload=normalized,
        )


def _decode_json_payload(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _normalize_runtime_defaults_payload(
    resource_id: object,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    orchestration = _mapping(payload.get("orchestration"))
    tool_worker = _mapping(payload.get("tool_worker"))
    daemon = _mapping(payload.get("daemon"))

    if not orchestration:
        orchestration = {
            "run_lease_seconds": payload.get("orchestration_run_lease_seconds"),
            "run_heartbeat_seconds": payload.get("orchestration_run_heartbeat_seconds"),
            "executor_max_concurrent_assignments": payload.get(
                "orchestration_executor_max_concurrent_assignments",
            ),
            "auto_compaction_enabled": payload.get(
                "orchestration_auto_compaction_enabled",
            ),
            "auto_compaction_reserve_tokens": payload.get(
                "orchestration_auto_compaction_reserve_tokens",
            ),
            "auto_compaction_soft_threshold_tokens": payload.get(
                "orchestration_auto_compaction_soft_threshold_tokens",
            ),
        }
    if not tool_worker:
        tool_worker = {
            "run_max_attempts": payload.get("tool_run_max_attempts"),
            "run_lease_seconds": payload.get("tool_run_lease_seconds"),
            "run_heartbeat_seconds": payload.get("tool_run_heartbeat_seconds"),
            "max_in_flight": payload.get("tool_worker_max_in_flight"),
            "default_run_concurrency": payload.get(
                "tool_worker_default_run_concurrency",
            ),
            "image_run_concurrency": payload.get("tool_worker_image_run_concurrency"),
            "shared_state_run_concurrency": payload.get(
                "tool_worker_shared_state_run_concurrency",
            ),
            "remote_default_max_concurrency": payload.get(
                "tool_remote_default_max_concurrency",
            ),
        }

    normalized: dict[str, Any] = {
        "config_id": str(
            payload.get("config_id")
            or payload.get("id")
            or resource_id
            or "defaults",
        ),
        "enabled": bool(payload.get("enabled", True)),
        "orchestration": _without_none(orchestration),
        "tool_worker": _without_none(tool_worker),
        "metadata": _mapping(payload.get("metadata")),
    }
    if daemon:
        normalized["daemon"] = _without_none(daemon)
    return normalized


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _without_none(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _update_json_payload(
    bind: sa.Connection,
    *,
    table_name: str,
    id_column: str,
    id_value: object,
    payload_column: str,
    payload: Mapping[str, Any],
) -> None:
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET {payload_column} = CAST(:payload AS JSON)
                WHERE {id_column} = :id_value
                """,
            ),
            {"payload": json.dumps(dict(payload)), "id_value": id_value},
        )
        return
    bind.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET {payload_column} = :payload
            WHERE {id_column} = :id_value
            """,
        ),
        {"payload": json.dumps(dict(payload)), "id_value": id_value},
    )
