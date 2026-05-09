"""authorization owned policy persistence

Revision ID: 0044_authorization_owned_persistence
Revises: 0043_settings_governance
Create Date: 2026-05-08 18:30:00
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "0044_authorization_owned_persistence"
down_revision = "0043_settings_governance"
branch_labels = None
depends_on = None

_ACTION_UPGRADE_MAP = {
    "tool.access_tool": "tool.authorize",
    "tool.access_effect": "tool.effect.authorize",
}
_ACTION_DOWNGRADE_MAP = {
    new: old for old, new in _ACTION_UPGRADE_MAP.items()
}
_EFFECT_UPGRADE_MAP = {
    "remote_tool_access": "remote_tool_execution",
    "sensitive_access": "sensitive_operation_confirmation",
}
_EFFECT_DOWNGRADE_MAP = {
    new: old for old, new in _EFFECT_UPGRADE_MAP.items()
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("authorization_policies"):
        op.create_table(
            "authorization_policies",
            sa.Column("policy_id", sa.String(length=160), nullable=False),
            sa.Column("description", sa.String(length=500), nullable=False),
            sa.Column("effect", sa.String(length=40), nullable=False),
            sa.Column("actions_payload", sa.JSON(), nullable=False),
            sa.Column("subject_type", sa.String(length=120), nullable=True),
            sa.Column("subject_id", sa.String(length=240), nullable=True),
            sa.Column("subject_match_payload", sa.JSON(), nullable=False),
            sa.Column("resource_kind", sa.String(length=120), nullable=True),
            sa.Column("resource_id", sa.String(length=240), nullable=True),
            sa.Column("resource_match_payload", sa.JSON(), nullable=False),
            sa.Column("context_match_payload", sa.JSON(), nullable=False),
            sa.Column("condition_payload", sa.JSON(), nullable=True),
            sa.Column("obligations_payload", sa.JSON(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("source_kind", sa.String(length=80), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("policy_id", name="pk_authorization_policies"),
        )
        _create_indexes(
            "authorization_policies",
            (
                ("ix_authorization_policies_effect", ["effect"]),
                ("ix_authorization_policies_subject_type", ["subject_type"]),
                ("ix_authorization_policies_subject_id", ["subject_id"]),
                ("ix_authorization_policies_resource_kind", ["resource_kind"]),
                ("ix_authorization_policies_resource_id", ["resource_id"]),
                ("ix_authorization_policies_priority", ["priority"]),
                ("ix_authorization_policies_enabled", ["enabled"]),
                ("ix_authorization_policies_source_kind", ["source_kind"]),
            ),
        )

    inspector = sa.inspect(bind)
    if not inspector.has_table("authorization_action_audits"):
        op.create_table(
            "authorization_action_audits",
            sa.Column("audit_id", sa.String(length=160), nullable=False),
            sa.Column("action", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("actor_type", sa.String(length=80), nullable=True),
            sa.Column("actor_id", sa.String(length=200), nullable=True),
            sa.Column("target_policy_id", sa.String(length=160), nullable=True),
            sa.Column("reason", sa.String(length=1000), nullable=False),
            sa.Column("before_payload", sa.JSON(), nullable=False),
            sa.Column("after_payload", sa.JSON(), nullable=False),
            sa.Column("decision_payload", sa.JSON(), nullable=False),
            sa.Column("metadata_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("audit_id", name="pk_authorization_action_audits"),
        )
        _create_indexes(
            "authorization_action_audits",
            (
                ("ix_authorization_action_audits_action", ["action"]),
                ("ix_authorization_action_audits_status", ["status"]),
                ("ix_authorization_action_audits_actor_type", ["actor_type"]),
                ("ix_authorization_action_audits_actor_id", ["actor_id"]),
                (
                    "ix_authorization_action_audits_target_policy_id",
                    ["target_policy_id"],
                ),
                ("ix_authorization_action_audits_created_at", ["created_at"]),
            ),
        )

    _migrate_access_policies_to_authorization(bind)
    _migrate_access_grants_to_authorization(bind)

    inspector = sa.inspect(bind)
    if inspector.has_table("access_temporary_grants"):
        _drop_table_with_indexes(
            "access_temporary_grants",
            (
                "ix_access_temporary_grants_updated_at",
                "ix_access_temporary_grants_expires_at",
                "ix_access_temporary_grants_status",
                "ix_access_temporary_grants_policy_id",
            ),
        )
    if inspector.has_table("access_authorization_policies"):
        _drop_table_with_indexes(
            "access_authorization_policies",
            (
                "ix_access_authorization_policies_updated_at",
                "ix_access_authorization_policies_status",
                "ix_access_authorization_policies_effect",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("access_authorization_policies"):
        op.create_table(
            "access_authorization_policies",
            sa.Column("policy_id", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("effect", sa.String(length=40), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("policy_spec", sa.JSON(), nullable=False),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint(
                "policy_id",
                name="pk_access_authorization_policies",
            ),
        )
        _create_indexes(
            "access_authorization_policies",
            (
                ("ix_access_authorization_policies_effect", ["effect"]),
                ("ix_access_authorization_policies_status", ["status"]),
                ("ix_access_authorization_policies_updated_at", ["updated_at"]),
            ),
        )

    if not inspector.has_table("access_temporary_grants"):
        op.create_table(
            "access_temporary_grants",
            sa.Column("grant_id", sa.String(length=160), nullable=False),
            sa.Column("policy_id", sa.String(length=120), nullable=True),
            sa.Column("subject", sa.JSON(), nullable=False),
            sa.Column("resource", sa.JSON(), nullable=False),
            sa.Column("scopes", sa.JSON(), nullable=False),
            sa.Column("effects", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("reason", sa.String(length=1000), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("redaction_policy", sa.JSON(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("grant_id", name="pk_access_temporary_grants"),
        )
        _create_indexes(
            "access_temporary_grants",
            (
                ("ix_access_temporary_grants_policy_id", ["policy_id"]),
                ("ix_access_temporary_grants_status", ["status"]),
                ("ix_access_temporary_grants_expires_at", ["expires_at"]),
                ("ix_access_temporary_grants_updated_at", ["updated_at"]),
            ),
        )

    _migrate_authorization_policies_to_access(bind)
    _migrate_authorization_grants_to_access(bind)

    inspector = sa.inspect(bind)
    if inspector.has_table("authorization_action_audits"):
        _drop_table_with_indexes(
            "authorization_action_audits",
            (
                "ix_authorization_action_audits_created_at",
                "ix_authorization_action_audits_target_policy_id",
                "ix_authorization_action_audits_actor_id",
                "ix_authorization_action_audits_actor_type",
                "ix_authorization_action_audits_status",
                "ix_authorization_action_audits_action",
            ),
        )

    inspector = sa.inspect(bind)
    if inspector.has_table("authorization_policies"):
        _drop_table_with_indexes(
            "authorization_policies",
            (
                "ix_authorization_policies_source_kind",
                "ix_authorization_policies_enabled",
                "ix_authorization_policies_priority",
                "ix_authorization_policies_resource_id",
                "ix_authorization_policies_resource_kind",
                "ix_authorization_policies_subject_id",
                "ix_authorization_policies_subject_type",
                "ix_authorization_policies_effect",
            ),
        )


def _migrate_access_policies_to_authorization(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    if (
        not inspector.has_table("access_authorization_policies")
        or not inspector.has_table("authorization_policies")
    ):
        return
    metadata = sa.MetaData()
    source = sa.Table("access_authorization_policies", metadata, autoload_with=bind)
    target = sa.Table("authorization_policies", metadata, autoload_with=bind)
    existing_ids = {
        row[0]
        for row in bind.execute(sa.select(target.c.policy_id)).all()
    }
    for row in bind.execute(sa.select(source)).mappings():
        policy_id = str(row["policy_id"]).strip()
        if not policy_id or policy_id in existing_ids:
            continue
        spec = _json_object(row["policy_spec"])
        subject = _json_object(spec.get("subject"))
        resource = _json_object(spec.get("resource"))
        context = _json_object(spec.get("context"))
        policy_metadata = _json_object(row["metadata"])
        created_at = row["created_at"] or _now()
        updated_at = row["updated_at"] or created_at
        bind.execute(
            target.insert().values(
                policy_id=policy_id,
                description=_optional_string(spec.get("description"))
                or _optional_string(row["name"])
                or policy_id,
                effect=_normalize_effect(row["effect"]),
                actions_payload=_mapped_strings(
                    _json_list(spec.get("actions")),
                    _ACTION_UPGRADE_MAP,
                ),
                subject_type=_optional_string(subject.get("type")),
                subject_id=_optional_string(subject.get("id")),
                subject_match_payload=_json_object(subject.get("match")),
                resource_kind=_optional_string(resource.get("kind")),
                resource_id=_optional_string(resource.get("id")),
                resource_match_payload=_json_object(resource.get("match")),
                context_match_payload=_json_object(context.get("match")),
                condition_payload=(
                    _json_object(spec.get("condition"))
                    if isinstance(_decode_json(spec.get("condition")), dict)
                    else None
                ),
                obligations_payload=_json_list(spec.get("obligations")),
                priority=_int_value(spec.get("priority")),
                enabled=(
                    str(row["status"]).strip().lower() == "active"
                    and bool(spec.get("enabled", True))
                ),
                source_kind=(
                    _optional_string(policy_metadata.get("authorization_source_kind"))
                    or "migrated_access"
                ),
                created_at=created_at,
                updated_at=updated_at,
            ),
        )
        existing_ids.add(policy_id)


def _migrate_access_grants_to_authorization(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    if (
        not inspector.has_table("access_temporary_grants")
        or not inspector.has_table("authorization_temporary_grants")
    ):
        return
    metadata = sa.MetaData()
    source = sa.Table("access_temporary_grants", metadata, autoload_with=bind)
    target = sa.Table("authorization_temporary_grants", metadata, autoload_with=bind)
    existing_ids = {row[0] for row in bind.execute(sa.select(target.c.id)).all()}
    for row in bind.execute(sa.select(source)).mappings():
        grant_id = str(row["grant_id"]).strip()
        if (
            not grant_id
            or grant_id in existing_ids
            or str(row["status"]).strip().lower() != "active"
        ):
            continue
        grant_metadata = _json_object(row["metadata"])
        run_id = _optional_string(grant_metadata.get("run_id"))
        session_key = _optional_string(grant_metadata.get("session_key"))
        scope = _optional_string(grant_metadata.get("grant_scope"))
        if scope not in {"run", "session"}:
            scope = "session" if session_key else "run"
        bind.execute(
            target.insert().values(
                id=grant_id,
                scope=scope,
                run_id=run_id,
                session_key=session_key,
                agent_id=_optional_string(grant_metadata.get("agent_id")),
                approval_request_id=_optional_string(
                    grant_metadata.get("approval_request_id"),
                ),
                effect_ids_payload=_mapped_strings(
                    _json_list(grant_metadata.get("effect_ids") or row["effects"]),
                    _EFFECT_UPGRADE_MAP,
                ),
                tool_ids_payload=_json_list(
                    grant_metadata.get("tool_ids") or row["scopes"],
                ),
                created_at=row["created_at"] or _now(),
            ),
        )
        existing_ids.add(grant_id)


def _migrate_authorization_policies_to_access(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    if (
        not inspector.has_table("authorization_policies")
        or not inspector.has_table("access_authorization_policies")
    ):
        return
    metadata = sa.MetaData()
    source = sa.Table("authorization_policies", metadata, autoload_with=bind)
    target = sa.Table("access_authorization_policies", metadata, autoload_with=bind)
    existing_ids = {row[0] for row in bind.execute(sa.select(target.c.policy_id)).all()}
    for row in bind.execute(sa.select(source)).mappings():
        policy_id = str(row["policy_id"]).strip()
        if not policy_id or policy_id in existing_ids:
            continue
        policy_spec = _policy_spec_from_authorization_row(row)
        bind.execute(
            target.insert().values(
                policy_id=policy_id[:120],
                name=(row["description"] or policy_id)[:200],
                effect=_normalize_effect(row["effect"]),
                version=1,
                status="active" if row["enabled"] else "disabled",
                policy_spec=policy_spec,
                redaction_policy={"mode": "metadata_only"},
                metadata={
                    "source": "authorization_owned_persistence_downgrade",
                    "authorization_source_kind": row["source_kind"],
                },
                created_at=row["created_at"] or _now(),
                updated_at=row["updated_at"] or _now(),
            ),
        )
        existing_ids.add(policy_id)


def _migrate_authorization_grants_to_access(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    if (
        not inspector.has_table("authorization_temporary_grants")
        or not inspector.has_table("access_temporary_grants")
    ):
        return
    metadata = sa.MetaData()
    source = sa.Table("authorization_temporary_grants", metadata, autoload_with=bind)
    target = sa.Table("access_temporary_grants", metadata, autoload_with=bind)
    existing_ids = {row[0] for row in bind.execute(sa.select(target.c.grant_id)).all()}
    for row in bind.execute(sa.select(source)).mappings():
        grant_id = str(row["id"]).strip()
        if not grant_id or grant_id in existing_ids:
            continue
        grant_metadata = {
            "source": "authorization_owned_persistence_downgrade",
            "grant_scope": row["scope"],
            "run_id": row["run_id"],
            "session_key": row["session_key"],
            "agent_id": row["agent_id"],
            "approval_request_id": row["approval_request_id"],
            "effect_ids": _mapped_strings(
                _json_list(row["effect_ids_payload"]),
                _EFFECT_DOWNGRADE_MAP,
            ),
            "tool_ids": _json_list(row["tool_ids_payload"]),
        }
        bind.execute(
            target.insert().values(
                grant_id=grant_id,
                policy_id=None,
                subject=_temporary_grant_subject(row),
                resource=_temporary_grant_resource(row),
                scopes=_json_list(row["tool_ids_payload"]),
                effects=_mapped_strings(
                    _json_list(row["effect_ids_payload"]),
                    _EFFECT_DOWNGRADE_MAP,
                ),
                status="active",
                reason="orchestration approval temporary grant",
                expires_at=None,
                revoked_at=None,
                redaction_policy={"mode": "metadata_only"},
                metadata=grant_metadata,
                created_at=row["created_at"] or _now(),
                updated_at=_now(),
            ),
        )
        existing_ids.add(grant_id)


def _policy_spec_from_authorization_row(row: sa.RowMapping) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "actions": _mapped_strings(
            _json_list(row["actions_payload"]),
            _ACTION_DOWNGRADE_MAP,
        ),
        "priority": _int_value(row["priority"]),
        "enabled": bool(row["enabled"]),
    }
    if row["description"]:
        spec["description"] = row["description"]
    subject: dict[str, Any] = {}
    if row["subject_type"]:
        subject["type"] = row["subject_type"]
    if row["subject_id"]:
        subject["id"] = row["subject_id"]
    if _json_object(row["subject_match_payload"]):
        subject["match"] = _json_object(row["subject_match_payload"])
    if subject:
        spec["subject"] = subject
    resource: dict[str, Any] = {}
    if row["resource_kind"]:
        resource["kind"] = row["resource_kind"]
    if row["resource_id"]:
        resource["id"] = row["resource_id"]
    if _json_object(row["resource_match_payload"]):
        resource["match"] = _json_object(row["resource_match_payload"])
    if resource:
        spec["resource"] = resource
    context_match = _json_object(row["context_match_payload"])
    if context_match:
        spec["context"] = {"match": context_match}
    condition = _json_object(row["condition_payload"])
    if condition:
        spec["condition"] = condition
    obligations = _json_list(row["obligations_payload"])
    if obligations:
        spec["obligations"] = obligations
    return spec


def _temporary_grant_subject(row: sa.RowMapping) -> dict[str, Any]:
    if row["agent_id"]:
        return {"kind": "agent", "id": row["agent_id"]}
    return {"kind": "orchestration", "id": row["run_id"] or row["session_key"] or row["id"]}


def _temporary_grant_resource(row: sa.RowMapping) -> dict[str, Any]:
    if row["scope"] == "run":
        return {"kind": "orchestration_run", "id": row["run_id"]}
    return {"kind": "session", "id": row["session_key"]}


def _drop_table_with_indexes(
    table_name: str,
    index_names: tuple[str, ...],
) -> None:
    existing_indexes = {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_indexes(table_name)
    }
    with op.batch_alter_table(table_name) as batch_op:
        for index_name in index_names:
            if index_name in existing_indexes:
                batch_op.drop_index(index_name)
    op.drop_table(table_name)


def _create_indexes(
    table_name: str,
    indexes: tuple[tuple[str, list[str]], ...],
) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        for index_name, columns in indexes:
            batch_op.create_index(index_name, columns)


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _json_object(value: Any) -> dict[str, Any]:
    decoded = _decode_json(value)
    return dict(decoded) if isinstance(decoded, dict) else {}


def _json_list(value: Any) -> list[Any]:
    decoded = _decode_json(value)
    if isinstance(decoded, list):
        return list(decoded)
    if isinstance(decoded, tuple):
        return list(decoded)
    return []


def _mapped_strings(values: list[Any], mapping: dict[str, str]) -> list[str]:
    return [
        mapping.get(value.strip(), value.strip())
        for value in (str(item) for item in values)
        if value.strip()
    ]


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_effect(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"allow", "deny"} else "deny"


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _now() -> datetime:
    return datetime.now(timezone.utc)
