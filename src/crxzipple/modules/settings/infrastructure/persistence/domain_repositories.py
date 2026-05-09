from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.settings.application.services import (
    SettingsActionService,
    SettingsEffectiveResolutionService,
    SettingsQueryService,
)
from crxzipple.modules.settings.application.setup import SettingsServices
from crxzipple.modules.settings.domain.entities import (
    SettingsActionAudit,
    SettingsEffectiveSnapshot,
    SettingsOverride,
    SettingsResource,
    SettingsResourceVersion,
)
from crxzipple.modules.settings.domain.exceptions import SettingsAlreadyExistsError
from crxzipple.modules.settings.domain.value_objects import SettingsValidationResult
from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsActionAuditModel,
    SettingsEffectiveSnapshotModel,
    SettingsOverrideModel,
    SettingsResourceModel,
    SettingsResourceVersionModel,
)
from crxzipple.modules.settings.infrastructure.persistence.repositories import (
    SettingsActionAuditRecord,
    SettingsEffectiveSnapshotRecord,
    SettingsOverrideRecord,
    SettingsResourceRecord,
    SettingsResourceVersionRecord,
    _action_audit_record,
    _apply_resource,
    _optional_text,
    _override_model,
    _override_record,
    _required_text,
    _resource_model,
    _resource_record,
    _snapshot_model,
    _snapshot_record,
    _version_model,
    _version_record,
)
from crxzipple.shared.settings import ConfigSource, SettingsResourceRef


JsonObject = dict[str, Any]


@dataclass(slots=True)
class SqlAlchemySettingsRepositories:
    resources: "SqlAlchemySettingsResourceRepository"
    versions: "SqlAlchemySettingsResourceVersionRepository"
    overrides: "SqlAlchemySettingsOverrideRepository"
    snapshots: "SqlAlchemySettingsEffectiveSnapshotRepository"
    audits: "SqlAlchemySettingsActionAuditDomainRepository"


def create_sqlalchemy_settings_services(
    session_factory: SessionFactory,
) -> SettingsServices:
    repositories = SqlAlchemySettingsRepositories(
        resources=SqlAlchemySettingsResourceRepository(session_factory),
        versions=SqlAlchemySettingsResourceVersionRepository(session_factory),
        overrides=SqlAlchemySettingsOverrideRepository(session_factory),
        snapshots=SqlAlchemySettingsEffectiveSnapshotRepository(session_factory),
        audits=SqlAlchemySettingsActionAuditDomainRepository(session_factory),
    )
    resolver = SettingsEffectiveResolutionService(
        resource_repository=repositories.resources,
        version_repository=repositories.versions,
        override_repository=repositories.overrides,
        snapshot_repository=repositories.snapshots,
    )
    actions = SettingsActionService(
        resource_repository=repositories.resources,
        version_repository=repositories.versions,
        override_repository=repositories.overrides,
        snapshot_repository=repositories.snapshots,
        audit_repository=repositories.audits,
        resolver=resolver,
    )
    queries = SettingsQueryService(
        resource_repository=repositories.resources,
        version_repository=repositories.versions,
        override_repository=repositories.overrides,
        snapshot_repository=repositories.snapshots,
        audit_repository=repositories.audits,
        resolver=resolver,
    )
    return SettingsServices(
        repositories=repositories,  # type: ignore[arg-type]
        actions=actions,
        queries=queries,
        resolver=resolver,
    )


class SqlAlchemySettingsResourceRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, resource: SettingsResource) -> None:
        if self.get(resource.id) is not None:
            raise SettingsAlreadyExistsError(
                f"settings resource '{resource.id}' already exists.",
            )
        with self._session_factory() as session:
            session.add(_resource_model(_resource_record_from_domain(resource)))
            session.commit()

    def save(self, resource: SettingsResource) -> None:
        with self._session_factory() as session:
            model = session.get(SettingsResourceModel, resource.id)
            if model is None:
                session.add(_resource_model(_resource_record_from_domain(resource)))
            else:
                _apply_resource(model, _resource_record_from_domain(resource))
            session.commit()

    def get(self, resource_id: str) -> SettingsResource | None:
        with self._session_factory() as session:
            model = session.get(
                SettingsResourceModel,
                _required_text(resource_id, "resource id"),
            )
            if model is None:
                return None
            return _resource_from_record(_resource_record(model))

    def list(
        self,
        *,
        resource_kind: str | None = None,
        owner_module: str | None = None,
    ) -> tuple[SettingsResource, ...]:
        with self._session_factory() as session:
            statement = select(SettingsResourceModel).order_by(
                SettingsResourceModel.resource_kind.asc(),
                SettingsResourceModel.resource_id.asc(),
            )
            if resource_kind is not None:
                statement = statement.where(
                    SettingsResourceModel.resource_kind
                    == _required_text(resource_kind, "resource kind"),
                )
            resources = tuple(
                _resource_from_record(_resource_record(model))
                for model in session.scalars(statement)
            )
        if owner_module is not None:
            normalized_owner = owner_module.strip()
            resources = tuple(
                resource
                for resource in resources
                if resource.owner_module == normalized_owner
            )
        return resources


class SqlAlchemySettingsResourceVersionRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, version: SettingsResourceVersion) -> None:
        if self.get(version.id) is not None:
            raise SettingsAlreadyExistsError(
                f"settings version '{version.id}' already exists.",
            )
        with self._session_factory() as session:
            model = _version_model(_version_record_from_domain(version))
            session.add(model)
            resource = session.get(SettingsResourceModel, version.resource_id)
            if resource is not None:
                _apply_version_to_resource(resource, model)
            session.commit()

    def save(self, version: SettingsResourceVersion) -> None:
        with self._session_factory() as session:
            model = session.get(SettingsResourceVersionModel, version.id)
            stored = _version_model(_version_record_from_domain(version))
            if model is None:
                session.add(stored)
                model = stored
            else:
                _apply_version(model, stored)
            resource = session.get(SettingsResourceModel, version.resource_id)
            if resource is not None:
                _apply_version_to_resource(resource, model)
            session.commit()

    def get(self, version_id: str) -> SettingsResourceVersion | None:
        with self._session_factory() as session:
            model = session.get(
                SettingsResourceVersionModel,
                _required_text(version_id, "version id"),
            )
            if model is None:
                return None
            return _version_from_record(_version_record(model))

    def list_for_resource(self, resource_id: str) -> tuple[SettingsResourceVersion, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(SettingsResourceVersionModel)
                .where(
                    SettingsResourceVersionModel.resource_id
                    == _required_text(resource_id, "resource id"),
                )
                .order_by(SettingsResourceVersionModel.version_number.asc()),
            ).all()
            return tuple(_version_from_record(_version_record(model)) for model in models)

    def latest_for_resource(self, resource_id: str) -> SettingsResourceVersion | None:
        versions = self.list_for_resource(resource_id)
        return versions[-1] if versions else None

    def latest_published_for_resource(
        self,
        resource_id: str,
    ) -> SettingsResourceVersion | None:
        with self._session_factory() as session:
            model = session.scalars(
                select(SettingsResourceVersionModel)
                .where(
                    SettingsResourceVersionModel.resource_id
                    == _required_text(resource_id, "resource id"),
                    SettingsResourceVersionModel.status == "published",
                )
                .order_by(
                    SettingsResourceVersionModel.version_number.desc(),
                    SettingsResourceVersionModel.created_at.desc(),
                )
                .limit(1),
            ).first()
            if model is None:
                return None
            return _version_from_record(_version_record(model))


class SqlAlchemySettingsOverrideRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, override: SettingsOverride) -> None:
        if self.get(override.id) is not None:
            raise SettingsAlreadyExistsError(
                f"settings override '{override.id}' already exists.",
            )
        with self._session_factory() as session:
            session.add(_override_model(_override_record_from_domain(override)))
            session.commit()

    def save(self, override: SettingsOverride) -> None:
        with self._session_factory() as session:
            model = session.get(SettingsOverrideModel, override.id)
            stored = _override_model(_override_record_from_domain(override))
            if model is None:
                session.add(stored)
            else:
                _apply_override(model, stored)
            session.commit()

    def get(self, override_id: str) -> SettingsOverride | None:
        with self._session_factory() as session:
            model = session.get(
                SettingsOverrideModel,
                _required_text(override_id, "override id"),
            )
            if model is None:
                return None
            return _override_from_record(_override_record(model))

    def list_for_resource(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        enabled_only: bool = False,
    ) -> tuple[SettingsOverride, ...]:
        with self._session_factory() as session:
            statement = (
                select(SettingsOverrideModel)
                .where(
                    SettingsOverrideModel.resource_id
                    == _required_text(resource_id, "resource id"),
                )
                .order_by(
                    SettingsOverrideModel.priority.asc(),
                    SettingsOverrideModel.override_id.asc(),
                )
            )
            if environment is not None:
                statement = statement.where(
                    SettingsOverrideModel.scope_key
                    == _required_text(environment, "environment"),
                )
            if enabled_only:
                statement = statement.where(SettingsOverrideModel.status == "active")
            return tuple(
                _override_from_record(_override_record(model))
                for model in session.scalars(statement)
            )


class SqlAlchemySettingsEffectiveSnapshotRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def add(self, snapshot: SettingsEffectiveSnapshot) -> None:
        record = _snapshot_record_from_domain(snapshot)
        with self._session_factory() as session:
            if record.is_current:
                previous = session.scalars(
                    select(SettingsEffectiveSnapshotModel).where(
                        SettingsEffectiveSnapshotModel.resource_id
                        == record.resource_id,
                        SettingsEffectiveSnapshotModel.scope_key == record.scope_key,
                        SettingsEffectiveSnapshotModel.is_current.is_(True),
                    ),
                ).all()
                for item in previous:
                    item.is_current = False
            session.add(_snapshot_model(record))
            session.commit()

    def get(self, snapshot_id: str) -> SettingsEffectiveSnapshot | None:
        with self._session_factory() as session:
            model = session.get(
                SettingsEffectiveSnapshotModel,
                _required_text(snapshot_id, "snapshot id"),
            )
            if model is None:
                return None
            return _snapshot_from_record(_snapshot_record(model))

    def latest_for_resource(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
    ) -> SettingsEffectiveSnapshot | None:
        scope_key = _optional_text(environment) or "default"
        with self._session_factory() as session:
            model = session.scalars(
                select(SettingsEffectiveSnapshotModel)
                .where(
                    SettingsEffectiveSnapshotModel.resource_id
                    == _required_text(resource_id, "resource id"),
                    SettingsEffectiveSnapshotModel.scope_key == scope_key,
                    SettingsEffectiveSnapshotModel.is_current.is_(True),
                )
                .order_by(
                    SettingsEffectiveSnapshotModel.generated_at.desc(),
                    SettingsEffectiveSnapshotModel.snapshot_id.desc(),
                )
                .limit(1),
            ).first()
            if model is None:
                return None
            return _snapshot_from_record(_snapshot_record(model))


class SqlAlchemySettingsActionAuditDomainRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._live_audits: dict[str, SettingsActionAudit] = {}

    def record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        reason: str,
        actor: str | None = None,
        risk: str | None = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> SettingsActionAudit:
        audit = SettingsActionAudit(
            id=f"settings_audit_{_uuid_hex()}",
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            actor=actor,
            risk=risk,
            request_metadata=dict(request_metadata or {}),
        )
        with self._session_factory() as session:
            session.add(_audit_model_from_domain(audit))
            session.commit()
        self._live_audits[audit.id] = audit
        return audit

    def mark_succeeded(
        self,
        audit_id: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> SettingsActionAudit:
        audit = self._require(audit_id)
        audit.mark_succeeded(result=result)
        self._save(audit)
        return audit

    def mark_failed(
        self,
        audit_id: str,
        *,
        error: dict[str, Any],
    ) -> SettingsActionAudit:
        audit = self._require(audit_id)
        audit.mark_failed(error=error)
        self._save(audit)
        return audit

    def get(self, audit_id: str) -> SettingsActionAudit | None:
        live = self._live_audits.get(audit_id)
        if live is not None:
            return live
        with self._session_factory() as session:
            model = session.get(
                SettingsActionAuditModel,
                _required_text(audit_id, "audit id"),
            )
            if model is None:
                return None
            return _audit_from_record(_action_audit_record(model))

    def list(self) -> tuple[SettingsActionAudit, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(SettingsActionAuditModel).order_by(
                    SettingsActionAuditModel.created_at.asc(),
                    SettingsActionAuditModel.audit_id.asc(),
                ),
            ).all()
            return tuple(_audit_from_record(_action_audit_record(model)) for model in models)

    def _require(self, audit_id: str) -> SettingsActionAudit:
        audit = self.get(audit_id)
        if audit is None:
            raise LookupError(f"Settings action audit '{audit_id}' does not exist.")
        return audit

    def _save(self, audit: SettingsActionAudit) -> None:
        with self._session_factory() as session:
            model = session.get(SettingsActionAuditModel, audit.id)
            stored = _audit_model_from_domain(audit)
            if model is None:
                session.add(stored)
            else:
                _apply_audit(model, stored)
            session.commit()
        self._live_audits[audit.id] = audit


def _resource_record_from_domain(resource: SettingsResource) -> SettingsResourceRecord:
    metadata = dict(resource.metadata)
    owner_module = str(metadata.get("owner_module") or resource.owner_module)
    metadata["owner_module"] = owner_module
    return SettingsResourceRecord(
        resource_id=resource.id,
        resource_kind=resource.resource_kind,
        governance_scope=resource.scope,
        config_contract=dict(
            metadata.get("config_contract")
            if isinstance(metadata.get("config_contract"), dict)
            else {"resource_kind": resource.resource_kind}
        ),
        storage_key=str(
            metadata.get("storage_key")
            or f"settings://{resource.resource_kind}/{resource.id}"
        ),
        display_name=resource.display_name,
        consumer_modules=tuple(
            metadata.get("consumer_modules")
            if isinstance(metadata.get("consumer_modules"), tuple)
            else tuple(metadata.get("consumer_modules") or (owner_module,))
        ),
        status=resource.status.value,
        published_version_id=resource.active_version_id,
        metadata=metadata,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
    )


def _resource_from_record(record: SettingsResourceRecord) -> SettingsResource:
    metadata = dict(record.metadata)
    owner_module = str(
        metadata.get("owner_module")
        or next(iter(record.consumer_modules), None)
        or "settings"
    )
    return SettingsResource(
        id=record.resource_id,
        resource_kind=record.resource_kind,
        owner_module=owner_module,
        scope=record.governance_scope,
        display_name=record.display_name,
        status=record.status,
        active_version_id=record.published_version_id,
        metadata=metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _version_record_from_domain(
    version: SettingsResourceVersion,
) -> SettingsResourceVersionRecord:
    metadata = dict(version.metadata)
    metadata["validation"] = version.validation.to_payload()
    return SettingsResourceVersionRecord(
        version_id=version.id,
        resource_id=version.resource_id,
        resource_kind=version.resource_kind,
        version_number=version.version_number,
        payload=dict(version.payload),
        status=version.status.value,
        source_kind=version.source,
        created_by=version.created_by,
        reason=version.reason,
        published_at=version.published_at,
        metadata=metadata,
        created_at=version.created_at,
        updated_at=version.published_at or version.created_at,
    )


def _version_from_record(record: SettingsResourceVersionRecord) -> SettingsResourceVersion:
    validation_payload = record.metadata.get("validation")
    validation = (
        SettingsValidationResult.from_payload(validation_payload)
        if isinstance(validation_payload, dict)
        else SettingsValidationResult(ok=record.status != "failed_validation")
    )
    return SettingsResourceVersion(
        id=record.version_id,
        resource_id=record.resource_id,
        resource_kind=record.resource_kind,
        payload=record.payload,
        version_number=record.version_number,
        status=record.status,
        validation=validation,
        source=record.source_kind,
        reason=record.reason,
        created_by=record.created_by,
        created_at=record.created_at,
        published_at=record.published_at,
        metadata=record.metadata,
    )


def _override_record_from_domain(override: SettingsOverride) -> SettingsOverrideRecord:
    return SettingsOverrideRecord(
        override_id=override.id,
        resource_id=override.resource_id,
        resource_kind=override.resource_kind,
        override_kind="environment",
        scope_key=override.environment,
        priority=override.priority,
        status="active" if override.enabled else "disabled",
        override_payload=dict(override.values),
        source_kind="settings",
        reason=override.reason,
        actor=override.created_by,
        metadata=dict(override.metadata),
        created_at=override.created_at,
        updated_at=override.updated_at,
    )


def _override_from_record(record: SettingsOverrideRecord) -> SettingsOverride:
    return SettingsOverride(
        id=record.override_id,
        resource_id=record.resource_id,
        resource_kind=record.resource_kind,
        environment=record.scope_key,
        values=record.override_payload,
        enabled=record.status == "active",
        priority=record.priority,
        reason=record.reason,
        created_by=record.actor,
        created_at=record.created_at,
        updated_at=record.updated_at,
        metadata=record.metadata,
    )


def _snapshot_record_from_domain(
    snapshot: SettingsEffectiveSnapshot,
) -> SettingsEffectiveSnapshotRecord:
    version_number = _version_number_from_sources(snapshot.sources)
    metadata = dict(snapshot.metadata)
    metadata["resource"] = snapshot.resource.to_payload()
    metadata["validation"] = snapshot.validation.to_payload()
    return SettingsEffectiveSnapshotRecord(
        snapshot_id=snapshot.id,
        resource_id=snapshot.resource.resource_id,
        resource_kind=snapshot.resource.resource_kind,
        scope_key=snapshot.environment or "default",
        version_id=snapshot.version_id,
        version_number=version_number,
        effective_payload=dict(snapshot.effective_value),
        sources=tuple(source.to_payload() for source in snapshot.sources),
        overrides_applied=tuple(source.to_payload() for source in snapshot.overrides),
        metadata=metadata,
        created_at=snapshot.created_at,
        generated_at=snapshot.created_at,
    )


def _snapshot_from_record(
    record: SettingsEffectiveSnapshotRecord,
) -> SettingsEffectiveSnapshot:
    resource_payload = record.metadata.get("resource")
    resource = (
        SettingsResourceRef.from_payload(resource_payload)
        if isinstance(resource_payload, dict)
        else SettingsResourceRef(
            resource_id=record.resource_id,
            resource_kind=record.resource_kind,
        )
    )
    validation_payload = record.metadata.get("validation")
    validation = (
        SettingsValidationResult.from_payload(validation_payload)
        if isinstance(validation_payload, dict)
        else SettingsValidationResult.ok_result()
    )
    return SettingsEffectiveSnapshot(
        id=record.snapshot_id,
        resource=resource,
        effective_value=record.effective_payload,
        sources=tuple(
            ConfigSource.from_payload(item)
            for item in record.sources
            if isinstance(item, dict)
        ),
        overrides=tuple(
            ConfigSource.from_payload(item)
            for item in record.overrides_applied
            if isinstance(item, dict)
        ),
        environment=None if record.scope_key == "default" else record.scope_key,
        version_id=record.version_id,
        validation=validation,
        created_at=record.generated_at or record.created_at,
        metadata=record.metadata,
    )


def _audit_model_from_domain(audit: SettingsActionAudit) -> SettingsActionAuditModel:
    return SettingsActionAuditModel(
        audit_id=audit.id,
        action_id=None,
        action_type=audit.action_type,
        target_type=audit.target_type,
        target_id=audit.target_id,
        resource_id=audit.target_id,
        resource_kind=audit.target_type,
        status=audit.status.value,
        actor=audit.actor,
        source="settings.application",
        reason=audit.reason,
        risk=audit.risk or "normal",
        confirmation=False,
        risk_acknowledged=False,
        request_metadata=dict(audit.request_metadata),
        result=dict(audit.result) if audit.result is not None else None,
        error=dict(audit.error) if audit.error is not None else None,
        redaction_policy=dict(audit.redaction_policy),
        trace_context={},
        created_at=audit.created_at,
        updated_at=audit.updated_at or audit.created_at,
    )


def _audit_from_record(record: SettingsActionAuditRecord) -> SettingsActionAudit:
    return SettingsActionAudit(
        id=record.audit_id,
        action_type=record.action_type,
        target_type=record.target_type,
        target_id=record.target_id,
        reason=record.reason,
        status=record.status,
        actor=record.actor,
        risk=record.risk,
        request_metadata=record.request_metadata,
        result=record.result,
        error=record.error,
        created_at=record.created_at,
        updated_at=record.updated_at,
        redaction_policy=record.redaction_policy,
    )


def _apply_version(
    model: SettingsResourceVersionModel,
    stored: SettingsResourceVersionModel,
) -> None:
    model.resource_id = stored.resource_id
    model.resource_kind = stored.resource_kind
    model.version_number = stored.version_number
    model.status = stored.status
    model.payload = stored.payload
    model.source_kind = stored.source_kind
    model.source_ref = stored.source_ref
    model.source_metadata = stored.source_metadata
    model.contract_version = stored.contract_version
    model.redaction_policy = stored.redaction_policy
    model.validation_result_id = stored.validation_result_id
    model.created_by = stored.created_by
    model.reason = stored.reason
    model.published_at = stored.published_at
    model.metadata_ = stored.metadata_
    model.created_at = stored.created_at
    model.updated_at = stored.updated_at


def _apply_version_to_resource(
    resource: SettingsResourceModel,
    version: SettingsResourceVersionModel,
) -> None:
    latest = resource.latest_version_number
    if latest is None or version.version_number > latest:
        resource.latest_version_number = version.version_number
    if version.status == "published":
        resource.published_version_id = version.version_id
        resource.published_version_number = version.version_number
        resource.updated_at = version.updated_at


def _apply_override(model: SettingsOverrideModel, stored: SettingsOverrideModel) -> None:
    model.resource_id = stored.resource_id
    model.resource_kind = stored.resource_kind
    model.override_kind = stored.override_kind
    model.scope_key = stored.scope_key
    model.priority = stored.priority
    model.status = stored.status
    model.override_payload = stored.override_payload
    model.source_kind = stored.source_kind
    model.source_ref = stored.source_ref
    model.reason = stored.reason
    model.actor = stored.actor
    model.expires_at = stored.expires_at
    model.redaction_policy = stored.redaction_policy
    model.metadata_ = stored.metadata_
    model.created_at = stored.created_at
    model.updated_at = stored.updated_at


def _apply_audit(model: SettingsActionAuditModel, stored: SettingsActionAuditModel) -> None:
    model.action_type = stored.action_type
    model.target_type = stored.target_type
    model.target_id = stored.target_id
    model.resource_id = stored.resource_id
    model.resource_kind = stored.resource_kind
    model.status = stored.status
    model.actor = stored.actor
    model.source = stored.source
    model.reason = stored.reason
    model.risk = stored.risk
    model.request_metadata = stored.request_metadata
    model.result = stored.result
    model.error = stored.error
    model.redaction_policy = stored.redaction_policy
    model.trace_context = stored.trace_context
    model.created_at = stored.created_at
    model.updated_at = stored.updated_at


def _version_number_from_sources(sources: tuple[ConfigSource, ...]) -> int | None:
    for source in sources:
        value = source.metadata.get("version_number")
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _uuid_hex() -> str:
    from uuid import uuid4

    return uuid4().hex
