"""effect metadata cleanup

Revision ID: 0019_effect_metadata_cleanup
Revises: 0018_tool_required_effect_ids
Create Date: 2026-03-24 15:00:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0019_effect_metadata_cleanup"
down_revision = "0018_tool_required_effect_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    orchestration_rows = bind.execute(
        sa.text(
            """
            SELECT id, metadata_payload
            FROM orchestration_runs
            """,
        ),
    ).all()
    for row in orchestration_rows:
        metadata = _decode_json_payload(row.metadata_payload)
        changed = False

        pending_request = metadata.get("pending_approval_request")
        if isinstance(pending_request, dict):
            if (
                pending_request.get("effect_id") is None
                and pending_request.get("capability_id") is not None
            ):
                pending_request["effect_id"] = pending_request["capability_id"]
                changed = True
            if "capability_id" in pending_request:
                pending_request.pop("capability_id", None)
                changed = True
            metadata["pending_approval_request"] = pending_request

        if "granted_effect_ids_once" not in metadata and isinstance(
            metadata.get("granted_capability_ids_once"),
            list,
        ):
            metadata["granted_effect_ids_once"] = list(
                metadata.get("granted_capability_ids_once", []),
            )
            changed = True
        if "granted_capability_ids_once" in metadata:
            metadata.pop("granted_capability_ids_once", None)
            changed = True

        if changed:
            bind.execute(
                sa.text(
                    """
                    UPDATE orchestration_runs
                    SET metadata_payload = :metadata_payload
                    WHERE id = :id
                    """,
                ),
                {
                    "id": row.id,
                    "metadata_payload": json.dumps(metadata),
                },
            )

    session_rows = bind.execute(
        sa.text(
            """
            SELECT id, metadata_payload
            FROM sessions
            """,
        ),
    ).all()
    for row in session_rows:
        metadata = _decode_json_payload(row.metadata_payload)
        changed = False
        tool_grants = metadata.get("tool_grants")
        if isinstance(tool_grants, dict):
            if "effect_ids" not in tool_grants and isinstance(
                tool_grants.get("capability_ids"),
                list,
            ):
                tool_grants["effect_ids"] = list(tool_grants.get("capability_ids", []))
                changed = True
            if "capability_ids" in tool_grants:
                tool_grants.pop("capability_ids", None)
                changed = True
            metadata["tool_grants"] = tool_grants
        if changed:
            bind.execute(
                sa.text(
                    """
                    UPDATE sessions
                    SET metadata_payload = :metadata_payload
                    WHERE id = :id
                    """,
                ),
                {
                    "id": row.id,
                    "metadata_payload": json.dumps(metadata),
                },
            )

    message_rows = bind.execute(
        sa.text(
            """
            SELECT id, content_payload
            FROM session_messages
            WHERE source_kind = 'capability_request'
            """,
        ),
    ).all()
    for row in message_rows:
        payload = _decode_json_payload(row.content_payload)
        changed = False
        if payload.get("effect_id") is None and payload.get("capability_id") is not None:
            payload["effect_id"] = payload["capability_id"]
            changed = True
        if "capability_id" in payload:
            payload.pop("capability_id", None)
            changed = True
        if changed:
            bind.execute(
                sa.text(
                    """
                    UPDATE session_messages
                    SET content_payload = :content_payload
                    WHERE id = :id
                    """,
                ),
                {
                    "id": row.id,
                    "content_payload": json.dumps(payload),
                },
            )


def downgrade() -> None:
    bind = op.get_bind()

    orchestration_rows = bind.execute(
        sa.text(
            """
            SELECT id, metadata_payload
            FROM orchestration_runs
            """,
        ),
    ).all()
    for row in orchestration_rows:
        metadata = _decode_json_payload(row.metadata_payload)
        changed = False

        pending_request = metadata.get("pending_approval_request")
        if isinstance(pending_request, dict):
            if (
                pending_request.get("capability_id") is None
                and pending_request.get("effect_id") is not None
            ):
                pending_request["capability_id"] = pending_request["effect_id"]
                changed = True
            metadata["pending_approval_request"] = pending_request

        if "granted_capability_ids_once" not in metadata and isinstance(
            metadata.get("granted_effect_ids_once"),
            list,
        ):
            metadata["granted_capability_ids_once"] = list(
                metadata.get("granted_effect_ids_once", []),
            )
            changed = True

        if changed:
            bind.execute(
                sa.text(
                    """
                    UPDATE orchestration_runs
                    SET metadata_payload = :metadata_payload
                    WHERE id = :id
                    """,
                ),
                {
                    "id": row.id,
                    "metadata_payload": json.dumps(metadata),
                },
            )

    session_rows = bind.execute(
        sa.text(
            """
            SELECT id, metadata_payload
            FROM sessions
            """,
        ),
    ).all()
    for row in session_rows:
        metadata = _decode_json_payload(row.metadata_payload)
        changed = False
        tool_grants = metadata.get("tool_grants")
        if isinstance(tool_grants, dict):
            if "capability_ids" not in tool_grants and isinstance(
                tool_grants.get("effect_ids"),
                list,
            ):
                tool_grants["capability_ids"] = list(tool_grants.get("effect_ids", []))
                changed = True
            metadata["tool_grants"] = tool_grants
        if changed:
            bind.execute(
                sa.text(
                    """
                    UPDATE sessions
                    SET metadata_payload = :metadata_payload
                    WHERE id = :id
                    """,
                ),
                {
                    "id": row.id,
                    "metadata_payload": json.dumps(metadata),
                },
            )

    message_rows = bind.execute(
        sa.text(
            """
            SELECT id, content_payload
            FROM session_messages
            WHERE source_kind = 'capability_request'
            """,
        ),
    ).all()
    for row in message_rows:
        payload = _decode_json_payload(row.content_payload)
        changed = False
        if payload.get("capability_id") is None and payload.get("effect_id") is not None:
            payload["capability_id"] = payload["effect_id"]
            changed = True
        if changed:
            bind.execute(
                sa.text(
                    """
                    UPDATE session_messages
                    SET content_payload = :content_payload
                    WHERE id = :id
                    """,
                ),
                {
                    "id": row.id,
                    "content_payload": json.dumps(payload),
                },
            )


def _decode_json_payload(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        decoded = json.loads(value)
        if isinstance(decoded, dict):
            return dict(decoded)
    return {}
