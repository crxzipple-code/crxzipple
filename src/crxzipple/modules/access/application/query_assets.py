from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from crxzipple.modules.access.application.read_models import (
    AccessAssetDetailReadModel,
    AccessAssetSummaryReadModel,
    AccessConsumerBindingReadModel,
    AccessReadinessReadModel,
    CredentialBindingReadModel,
)
from crxzipple.modules.access.application.repositories import AccessAssetRecord


JsonObject = dict[str, Any]


def synthetic_asset_summaries(
    assets: tuple[AccessAssetRecord, ...],
    *,
    credentials: tuple[CredentialBindingReadModel, ...],
    consumers: tuple[AccessConsumerBindingReadModel, ...],
    readiness: tuple[AccessReadinessReadModel, ...],
) -> tuple[AccessAssetSummaryReadModel, ...]:
    explicit_asset_ids = {item.asset_id for item in assets}
    groups = _credential_groups_without_explicit_asset(
        credentials,
        explicit_asset_ids=explicit_asset_ids,
    )
    summaries: list[AccessAssetSummaryReadModel] = []
    for asset_id in sorted(groups):
        group = groups[asset_id]
        asset_consumers = consumers_for_asset(
            asset_id,
            credentials=group,
            consumers=consumers,
        )
        summaries.append(
            AccessAssetSummaryReadModel(
                asset_id=asset_id,
                asset_kind=_synthetic_asset_kind(group),
                display_name=_synthetic_asset_display_name(asset_id, group),
                governance_scope=_synthetic_governance_scope(group),
                status=_credential_group_status(group),
                readiness=_readiness_for_asset_group(
                    readiness,
                    asset_id=asset_id,
                    credentials=group,
                ),
                consumer_modules=unique_strings(
                    tuple(item.consumer_module for item in asset_consumers),
                ),
                credential_binding_count=len(group),
                metadata=_synthetic_asset_metadata(asset_id, group),
            ),
        )
    return tuple(summaries)


def synthetic_asset_detail(
    asset_id: str,
    *,
    credentials: tuple[CredentialBindingReadModel, ...],
    consumers: tuple[AccessConsumerBindingReadModel, ...],
    readiness: tuple[AccessReadinessReadModel, ...],
) -> AccessAssetDetailReadModel | None:
    group = tuple(
        item
        for item in credentials
        if _credential_asset_id(item) == asset_id
    )
    if not group:
        return None
    asset_consumers = consumers_for_asset(
        asset_id,
        credentials=group,
        consumers=consumers,
    )
    return AccessAssetDetailReadModel(
        asset_id=asset_id,
        asset_kind=_synthetic_asset_kind(group),
        display_name=_synthetic_asset_display_name(asset_id, group),
        governance_scope=_synthetic_governance_scope(group),
        status=_credential_group_status(group),
        secret_policy={
            "mode": "metadata_only",
            "managed_by": "settings.access_config",
            "binding_kinds": unique_strings(tuple(item.binding_kind for item in group)),
        },
        storage_key=None,
        consumer_modules=unique_strings(
            tuple(item.consumer_module for item in asset_consumers),
        ),
        readiness_policy={
            "target_kind": "credential_binding" if len(group) == 1 else "asset",
        },
        rotation_policy={},
        audit_required=True,
        export_policy={"secret_values": "never"},
        readiness=_readiness_for_asset_group(
            readiness,
            asset_id=asset_id,
            credentials=group,
        ),
        credential_bindings=group,
        consumer_bindings=asset_consumers,
        metadata=_synthetic_asset_metadata(asset_id, group),
        created_at=_earliest_datetime(tuple(item.created_at for item in group)),
        updated_at=_latest_datetime(tuple(item.updated_at for item in group)),
    )


def consumers_for_asset(
    asset_id: str,
    *,
    credentials: tuple[CredentialBindingReadModel, ...],
    consumers: tuple[AccessConsumerBindingReadModel, ...],
) -> tuple[AccessConsumerBindingReadModel, ...]:
    binding_ids = {item.binding_id for item in credentials}
    return tuple(
        consumer
        for consumer in consumers
        if consumer.asset_id == asset_id
        or _consumer_uses_credential_binding(consumer, binding_ids)
    )


def unique_strings(values: tuple[str | None, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)


def _credential_groups_without_explicit_asset(
    credentials: tuple[CredentialBindingReadModel, ...],
    *,
    explicit_asset_ids: set[str],
) -> dict[str, tuple[CredentialBindingReadModel, ...]]:
    grouped: dict[str, list[CredentialBindingReadModel]] = {}
    for credential in credentials:
        asset_id = _credential_asset_id(credential)
        if asset_id in explicit_asset_ids:
            continue
        grouped.setdefault(asset_id, []).append(credential)
    return {asset_id: tuple(items) for asset_id, items in grouped.items()}


def _credential_asset_id(binding: CredentialBindingReadModel) -> str:
    return binding.asset_id or binding.binding_id


def _synthetic_asset_kind(
    credentials: tuple[CredentialBindingReadModel, ...],
) -> str:
    if len(credentials) == 1:
        return "credential_binding"
    return "credential_bundle"


def _synthetic_governance_scope(
    credentials: tuple[CredentialBindingReadModel, ...],
) -> str:
    source_kinds = unique_strings(tuple(item.source_kind for item in credentials))
    if len(source_kinds) == 1:
        return source_kinds[0]
    return "mixed"


def _synthetic_asset_display_name(
    asset_id: str,
    credentials: tuple[CredentialBindingReadModel, ...],
) -> str:
    for credential in credentials:
        label = _metadata_text(credential.metadata, "display_name", "name", "label")
        if label:
            return label
    if len(credentials) == 1:
        return _title_from_identifier(credentials[0].binding_id)
    return _title_from_identifier(asset_id)


def _credential_group_status(
    credentials: tuple[CredentialBindingReadModel, ...],
) -> str:
    statuses = tuple(
        item.status.strip().lower()
        for item in credentials
        if item.status.strip()
    )
    if not statuses:
        return "unknown"
    if any(item == "active" for item in statuses):
        return "active"
    if len(set(statuses)) == 1:
        return statuses[0]
    if any(item == "revoked" for item in statuses):
        return "revoked"
    return statuses[0]


def _readiness_for_asset_group(
    readiness: tuple[AccessReadinessReadModel, ...],
    *,
    asset_id: str,
    credentials: tuple[CredentialBindingReadModel, ...],
) -> AccessReadinessReadModel | None:
    direct = next(
        (
            item
            for item in readiness
            if item.target_kind == "asset" and item.target_id == asset_id
        ),
        None,
    )
    if direct is not None:
        return direct
    if len(credentials) == 1:
        credential = credentials[0]
        return next(
            (
                item
                for item in readiness
                if item.target_kind == "credential_binding"
                and item.target_id == credential.binding_id
            ),
            None,
        )
    return None


def _consumer_uses_credential_binding(
    consumer: AccessConsumerBindingReadModel,
    binding_ids: set[str],
) -> bool:
    if not binding_ids:
        return False
    if consumer.credential_binding_id in binding_ids:
        return True
    return bool(set(consumer.credential_bindings.values()) & binding_ids)


def _synthetic_asset_metadata(
    asset_id: str,
    credentials: tuple[CredentialBindingReadModel, ...],
) -> JsonObject:
    binding_ids = tuple(item.binding_id for item in credentials)
    metadata: JsonObject = {
        "source": "settings.access_config",
        "synthetic": True,
        "asset_id_source": (
            "asset_id"
            if any(item.asset_id == asset_id for item in credentials)
            else "binding_id"
        ),
        "binding_ids": list(binding_ids),
        "binding_kinds": unique_strings(tuple(item.binding_kind for item in credentials)),
        "source_kinds": unique_strings(tuple(item.source_kind for item in credentials)),
    }
    if len(credentials) == 1:
        credential = credentials[0]
        metadata["credential_binding_id"] = credential.binding_id
        metadata["binding_kind"] = credential.binding_kind
        metadata["source_kind"] = credential.source_kind
        if credential.masked_preview:
            metadata["masked_preview"] = _safe_masked_preview(
                credential.source_kind,
                credential.masked_preview,
            )
    return metadata


def _safe_masked_preview(source_kind: str, masked_preview: str) -> str:
    normalized_kind = source_kind.strip().lower()
    if normalized_kind in {"env", "file"}:
        return f"{normalized_kind}:***"
    if normalized_kind in {"literal", "inline", "inline_credential", "secret"}:
        return "***"
    return masked_preview


def _metadata_text(
    metadata: Mapping[str, object],
    *keys: str,
) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _title_from_identifier(value: str) -> str:
    normalized = value.rsplit(":", 1)[-1]
    parts = [
        part
        for part in "".join(
            char if char.isalnum() else " "
            for char in normalized
        ).split()
        if part
    ]
    if not parts:
        return value
    return " ".join(part[:1].upper() + part[1:] for part in parts)


def _earliest_datetime(values: tuple[datetime | None, ...]) -> datetime | None:
    present = tuple(item for item in values if item is not None)
    return min(present) if present else None


def _latest_datetime(values: tuple[datetime | None, ...]) -> datetime | None:
    present = tuple(item for item in values if item is not None)
    return max(present) if present else None
