"""add explicit orchestration run wait state fields

Revision ID: 0068_orchestration_run_wait_state_fields
Revises: 0067_event_outbox
Create Date: 2026-06-02 00:00:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0068_orchestration_run_wait_state_fields"
down_revision = "0067_event_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orchestration_runs",
        sa.Column("pending_approval_request_payload", sa.JSON(), nullable=True),
    )
    op.add_column(
        "orchestration_runs",
        sa.Column("last_approval_resolution_payload", sa.JSON(), nullable=True),
    )
    op.add_column(
        "orchestration_runs",
        sa.Column("recovery_contract_payload", sa.JSON(), nullable=True),
    )
    _migrate_wait_state_out_of_metadata()


def downgrade() -> None:
    _restore_wait_state_to_metadata()
    op.drop_column("orchestration_runs", "recovery_contract_payload")
    op.drop_column("orchestration_runs", "last_approval_resolution_payload")
    op.drop_column("orchestration_runs", "pending_approval_request_payload")


def _migrate_wait_state_out_of_metadata() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, metadata_payload
            FROM orchestration_runs
            """,
        ),
    ).all()
    for row in rows:
        metadata = _decode_json_payload(row.metadata_payload)
        pending_approval = metadata.pop("pending_approval_request", None)
        last_resolution = metadata.pop("last_approval_resolution", None)
        recovery_contract = metadata.pop("recovery_contract", None)
        if not any(
            isinstance(value, dict)
            for value in (pending_approval, last_resolution, recovery_contract)
        ):
            continue
        bind.execute(
            sa.text(
                """
                UPDATE orchestration_runs
                SET
                    pending_approval_request_payload = :pending_approval_request_payload,
                    last_approval_resolution_payload = :last_approval_resolution_payload,
                    recovery_contract_payload = :recovery_contract_payload,
                    metadata_payload = :metadata_payload
                WHERE id = :id
                """,
            ),
            {
                "id": row.id,
                "pending_approval_request_payload": _json_or_none(pending_approval),
                "last_approval_resolution_payload": _json_or_none(last_resolution),
                "recovery_contract_payload": _json_or_none(recovery_contract),
                "metadata_payload": json.dumps(metadata),
            },
        )


def _restore_wait_state_to_metadata() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT
                id,
                metadata_payload,
                pending_approval_request_payload,
                last_approval_resolution_payload,
                recovery_contract_payload
            FROM orchestration_runs
            """,
        ),
    ).all()
    for row in rows:
        metadata = _decode_json_payload(row.metadata_payload)
        changed = False
        for key, value in (
            ("pending_approval_request", row.pending_approval_request_payload),
            ("last_approval_resolution", row.last_approval_resolution_payload),
            ("recovery_contract", row.recovery_contract_payload),
        ):
            payload = _decode_optional_json_payload(value)
            if payload is not None:
                metadata[key] = payload
                changed = True
        if not changed:
            continue
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


def _decode_json_payload(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        loaded = json.loads(value)
        return dict(loaded) if isinstance(loaded, dict) else {}
    return {}


def _decode_optional_json_payload(value: object) -> dict[str, object] | None:
    decoded = _decode_json_payload(value)
    return decoded or None


def _json_or_none(value: object) -> str | None:
    return json.dumps(value) if isinstance(value, dict) else None
