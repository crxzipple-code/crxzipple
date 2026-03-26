"""effect request terminology cleanup

Revision ID: 0020_effect_request_terminology
Revises: 0019_effect_metadata_cleanup
Create Date: 2026-03-24 18:30:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0020_effect_request_terminology"
down_revision = "0019_effect_metadata_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    message_rows = bind.execute(
        sa.text(
            """
            SELECT id, source_kind, content_payload, metadata_payload
            FROM session_messages
            """,
        ),
    ).all()
    for row in message_rows:
        source_kind = row.source_kind
        content_payload = _decode_json_payload(row.content_payload)
        metadata_payload = _decode_json_payload(row.metadata_payload)
        changed = False

        if source_kind == "capability_request":
            source_kind = "effect_request"
            changed = True

        if content_payload.get("tool_name") == "request_capability":
            content_payload["tool_name"] = "request_effect_access"
            changed = True
        if content_payload.get("name") == "request_capability":
            content_payload["name"] = "request_effect_access"
            changed = True

        if metadata_payload.get("tool_name") == "request_capability":
            metadata_payload["tool_name"] = "request_effect_access"
            changed = True
        if metadata_payload.get("synthetic_capability_request") is True:
            metadata_payload["synthetic_effect_request"] = True
            metadata_payload.pop("synthetic_capability_request", None)
            changed = True

        if changed:
            bind.execute(
                sa.text(
                    """
                    UPDATE session_messages
                    SET source_kind = :source_kind,
                        content_payload = :content_payload,
                        metadata_payload = :metadata_payload
                    WHERE id = :id
                    """,
                ),
                {
                    "id": row.id,
                    "source_kind": source_kind,
                    "content_payload": json.dumps(content_payload),
                    "metadata_payload": json.dumps(metadata_payload),
                },
            )


def downgrade() -> None:
    bind = op.get_bind()
    message_rows = bind.execute(
        sa.text(
            """
            SELECT id, source_kind, content_payload, metadata_payload
            FROM session_messages
            """,
        ),
    ).all()
    for row in message_rows:
        source_kind = row.source_kind
        content_payload = _decode_json_payload(row.content_payload)
        metadata_payload = _decode_json_payload(row.metadata_payload)
        changed = False

        if source_kind == "effect_request":
            source_kind = "capability_request"
            changed = True

        if content_payload.get("tool_name") == "request_effect_access":
            content_payload["tool_name"] = "request_capability"
            changed = True
        if content_payload.get("name") == "request_effect_access":
            content_payload["name"] = "request_capability"
            changed = True

        if metadata_payload.get("tool_name") == "request_effect_access":
            metadata_payload["tool_name"] = "request_capability"
            changed = True
        if metadata_payload.get("synthetic_effect_request") is True:
            metadata_payload["synthetic_capability_request"] = True
            metadata_payload.pop("synthetic_effect_request", None)
            changed = True

        if changed:
            bind.execute(
                sa.text(
                    """
                    UPDATE session_messages
                    SET source_kind = :source_kind,
                        content_payload = :content_payload,
                        metadata_payload = :metadata_payload
                    WHERE id = :id
                    """,
                ),
                {
                    "id": row.id,
                    "source_kind": source_kind,
                    "content_payload": json.dumps(content_payload),
                    "metadata_payload": json.dumps(metadata_payload),
                },
            )


def _decode_json_payload(raw_value: str | None) -> dict[str, object]:
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
