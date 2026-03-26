"""cleanup legacy agent tool preference keys

Revision ID: 0022_agent_tool_preferences_cleanup
Revises: 0021_agent_tool_preferences_payload
Create Date: 2026-03-24 23:10:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0022_agent_tool_preferences_cleanup"
down_revision = "0021_agent_tool_preferences_payload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, tool_preferences_payload
            FROM agents
            """,
        ),
    ).all()
    for row in rows:
        payload = _decode_json_payload(row.tool_preferences_payload)
        normalized = _normalize_preferences_payload(payload)
        if normalized == payload:
            continue
        bind.execute(
            sa.text(
                """
                UPDATE agents
                SET tool_preferences_payload = :payload
                WHERE id = :id
                """,
            ),
            {
                "id": row.id,
                "payload": json.dumps(normalized),
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, tool_preferences_payload
            FROM agents
            """,
        ),
    ).all()
    for row in rows:
        payload = _decode_json_payload(row.tool_preferences_payload)
        restored = _restore_legacy_preferences_payload(payload)
        if restored == payload:
            continue
        bind.execute(
            sa.text(
                """
                UPDATE agents
                SET tool_preferences_payload = :payload
                WHERE id = :id
                """,
            ),
            {
                "id": row.id,
                "payload": json.dumps(restored),
            },
        )


def _decode_json_payload(raw_value: str | dict[str, object] | None) -> dict[str, object]:
    if raw_value is None:
        return {}
    if isinstance(raw_value, dict):
        return dict(raw_value)
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_preferences_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    if "requested_effect_ids" not in normalized and isinstance(
        normalized.get("allowed_effect_ids"),
        list,
    ):
        normalized["requested_effect_ids"] = list(normalized["allowed_effect_ids"])
    if "requested_tool_ids" not in normalized and isinstance(
        normalized.get("allowed_tool_ids"),
        list,
    ):
        normalized["requested_tool_ids"] = list(normalized["allowed_tool_ids"])
    if "preferred_tags" not in normalized and isinstance(
        normalized.get("allowed_tags"),
        list,
    ):
        normalized["preferred_tags"] = list(normalized["allowed_tags"])
    if "prefers_background_tools" not in normalized and isinstance(
        normalized.get("allow_background_tools"),
        bool,
    ):
        normalized["prefers_background_tools"] = normalized["allow_background_tools"]
    if "prefers_mutating_tools" not in normalized and isinstance(
        normalized.get("allow_mutating_tools"),
        bool,
    ):
        normalized["prefers_mutating_tools"] = normalized["allow_mutating_tools"]
    normalized.pop("default_mode", None)
    normalized.pop("allowed_effect_ids", None)
    normalized.pop("denied_effect_ids", None)
    normalized.pop("allowed_tool_ids", None)
    normalized.pop("denied_tool_ids", None)
    normalized.pop("allowed_tags", None)
    normalized.pop("denied_tags", None)
    normalized.pop("allow_background_tools", None)
    normalized.pop("allow_mutating_tools", None)
    return normalized


def _restore_legacy_preferences_payload(payload: dict[str, object]) -> dict[str, object]:
    restored = dict(payload)
    if "allowed_effect_ids" not in restored and isinstance(
        restored.get("requested_effect_ids"),
        list,
    ):
        restored["allowed_effect_ids"] = list(restored["requested_effect_ids"])
    if "allowed_tool_ids" not in restored and isinstance(
        restored.get("requested_tool_ids"),
        list,
    ):
        restored["allowed_tool_ids"] = list(restored["requested_tool_ids"])
    if "allowed_tags" not in restored and isinstance(
        restored.get("preferred_tags"),
        list,
    ):
        restored["allowed_tags"] = list(restored["preferred_tags"])
    if "allow_background_tools" not in restored and isinstance(
        restored.get("prefers_background_tools"),
        bool,
    ):
        restored["allow_background_tools"] = restored["prefers_background_tools"]
    if "allow_mutating_tools" not in restored and isinstance(
        restored.get("prefers_mutating_tools"),
        bool,
    ):
        restored["allow_mutating_tools"] = restored["prefers_mutating_tools"]
    if "default_mode" not in restored:
        restored["default_mode"] = "allow"
    restored.pop("requested_effect_ids", None)
    restored.pop("requested_tool_ids", None)
    restored.pop("preferred_tags", None)
    restored.pop("prefers_background_tools", None)
    restored.pop("prefers_mutating_tools", None)
    return restored
