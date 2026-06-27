from __future__ import annotations

from crxzipple.modules.skills.domain import (
    SkillEnablementPolicy,
    SkillEnablementTargetKind,
    SkillInstallation,
    SkillInstallationStatus,
    SkillPackageIndex,
    SkillPackageStatus,
    SkillReadinessSnapshot,
    SkillRuntimeVisibility,
    SkillSource,
    SkillSourceStatus,
    SkillSourceSyncStatus,
    SkillSourceType,
)
from crxzipple.modules.skills.infrastructure.persistence.models import (
    SkillEnablementPolicyModel,
    SkillInstallationModel,
    SkillPackageIndexModel,
    SkillReadinessSnapshotModel,
    SkillSourceModel,
)
from crxzipple.modules.skills.infrastructure.persistence.repository_payloads import (
    requirements_from_payload,
)
from crxzipple.shared.time import coerce_optional_utc_datetime, coerce_utc_datetime


def source_model(source: SkillSource) -> SkillSourceModel:
    return SkillSourceModel(**source_mapping(source))


def source_mapping(source: SkillSource) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "source_type": source.source_type.value,
        "root_uri": source.root_uri,
        "status": source.status.value,
        "sync_status": source.sync_status.value,
        "scope": source.scope,
        "priority": source.priority,
        "enabled": source.enabled,
        "readonly": source.readonly,
        "metadata_payload": dict(source.metadata),
        "last_synced_at": source.last_synced_at,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
    }


def apply_source(model: SkillSourceModel, source: SkillSource) -> None:
    for key, value in source_mapping(source).items():
        setattr(model, key, value)


def source_record(model: SkillSourceModel) -> SkillSource:
    return SkillSource(
        source_id=model.source_id,
        source_type=SkillSourceType(model.source_type),
        root_uri=model.root_uri,
        status=SkillSourceStatus(model.status),
        sync_status=SkillSourceSyncStatus(model.sync_status),
        scope=model.scope,
        priority=model.priority,
        enabled=model.enabled,
        readonly=model.readonly,
        metadata=dict(model.metadata_payload or {}),
        last_synced_at=coerce_optional_utc_datetime(model.last_synced_at),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def package_model(package: SkillPackageIndex) -> SkillPackageIndexModel:
    return SkillPackageIndexModel(**package_mapping(package))


def package_mapping(package: SkillPackageIndex) -> dict[str, object]:
    return {
        "package_id": package.package_id,
        "skill_id": package.skill_id,
        "name": package.name,
        "source_id": package.source_id,
        "root_uri": package.root_uri,
        "manifest_uri": package.manifest_uri,
        "instructions_uri": package.instructions_uri,
        "version": package.version,
        "fingerprint": package.fingerprint,
        "status": package.status.value,
        "requirements_payload": package.requirements.to_payload(),
        "capability_requirements_payload": dict(package.capability_requirements),
        "metadata_payload": dict(package.metadata),
        "indexed_at": package.indexed_at,
        "updated_at": package.updated_at,
    }


def apply_package(model: SkillPackageIndexModel, package: SkillPackageIndex) -> None:
    for key, value in package_mapping(package).items():
        setattr(model, key, value)


def package_record(model: SkillPackageIndexModel) -> SkillPackageIndex:
    return SkillPackageIndex(
        package_id=model.package_id,
        skill_id=model.skill_id,
        name=model.name,
        source_id=model.source_id,
        root_uri=model.root_uri,
        manifest_uri=model.manifest_uri,
        instructions_uri=model.instructions_uri,
        version=model.version,
        fingerprint=model.fingerprint,
        status=SkillPackageStatus(model.status),
        requirements=requirements_from_payload(model.requirements_payload),
        capability_requirements=dict(model.capability_requirements_payload or {}),
        metadata=dict(model.metadata_payload or {}),
        indexed_at=coerce_utc_datetime(model.indexed_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def policy_model(policy: SkillEnablementPolicy) -> SkillEnablementPolicyModel:
    return SkillEnablementPolicyModel(**policy_mapping(policy))


def policy_mapping(policy: SkillEnablementPolicy) -> dict[str, object]:
    return {
        "policy_id": policy.policy_id,
        "target_kind": policy.target_kind.value,
        "target_id": policy.target_id,
        "enabled": policy.enabled,
        "trusted": policy.trusted,
        "runtime_visibility": policy.runtime_visibility.value,
        "priority": policy.priority,
        "reason": policy.reason,
        "metadata_payload": dict(policy.metadata),
        "created_at": policy.created_at,
        "updated_at": policy.updated_at,
    }


def apply_policy(
    model: SkillEnablementPolicyModel,
    policy: SkillEnablementPolicy,
) -> None:
    for key, value in policy_mapping(policy).items():
        setattr(model, key, value)


def policy_record(model: SkillEnablementPolicyModel) -> SkillEnablementPolicy:
    return SkillEnablementPolicy(
        policy_id=model.policy_id,
        target_kind=SkillEnablementTargetKind(model.target_kind),
        target_id=model.target_id,
        enabled=model.enabled,
        trusted=model.trusted,
        runtime_visibility=SkillRuntimeVisibility(model.runtime_visibility),
        priority=model.priority,
        reason=model.reason,
        metadata=dict(model.metadata_payload or {}),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def readiness_model(snapshot: SkillReadinessSnapshot) -> SkillReadinessSnapshotModel:
    return SkillReadinessSnapshotModel(
        skill_id=snapshot.skill_id,
        source_id=snapshot.source_id,
        status=snapshot.status.value,
        checks_payload=[dict(check) for check in snapshot.checks],
        reason=snapshot.reason,
        metadata_payload=dict(snapshot.metadata),
        updated_at=snapshot.updated_at,
    )


def apply_readiness(
    model: SkillReadinessSnapshotModel,
    snapshot: SkillReadinessSnapshot,
) -> None:
    replacement = readiness_model(snapshot)
    for key in (
        "source_id",
        "status",
        "checks_payload",
        "reason",
        "metadata_payload",
        "updated_at",
    ):
        setattr(model, key, getattr(replacement, key))


def readiness_record(model: SkillReadinessSnapshotModel) -> SkillReadinessSnapshot:
    return SkillReadinessSnapshot(
        skill_id=model.skill_id,
        source_id=model.source_id,
        status=model.status,
        checks=tuple(dict(check) for check in (model.checks_payload or [])),
        reason=model.reason,
        metadata=dict(model.metadata_payload or {}),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def installation_model(installation: SkillInstallation) -> SkillInstallationModel:
    return SkillInstallationModel(**installation_mapping(installation))


def installation_mapping(installation: SkillInstallation) -> dict[str, object]:
    return {
        "installation_id": installation.installation_id,
        "action": installation.action,
        "status": installation.status.value,
        "source_id": installation.source_id,
        "skill_id": installation.skill_id,
        "skill_name": installation.skill_name,
        "source_uri": installation.source_uri,
        "target_uri": installation.target_uri,
        "actor_id": installation.actor_id,
        "reason": installation.reason,
        "message": installation.message,
        "metadata_payload": dict(installation.metadata),
        "created_at": installation.created_at,
    }


def installation_record(model: SkillInstallationModel) -> SkillInstallation:
    return SkillInstallation(
        installation_id=model.installation_id,
        action=model.action,
        status=SkillInstallationStatus(model.status),
        source_id=model.source_id,
        skill_id=model.skill_id,
        skill_name=model.skill_name,
        source_uri=model.source_uri,
        target_uri=model.target_uri,
        actor_id=model.actor_id,
        reason=model.reason,
        message=model.message,
        metadata=dict(model.metadata_payload or {}),
        created_at=coerce_utc_datetime(model.created_at),
    )
