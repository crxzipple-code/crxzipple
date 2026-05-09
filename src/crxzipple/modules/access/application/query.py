from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.access.application.read_models import (
    AccessAssetDetailReadModel,
    AccessAssetListReadModel,
    AccessAssetSummaryReadModel,
    AccessAuditReadModel,
    AccessConsumerBindingReadModel,
    AccessOverviewReadModel,
    AccessReadinessReadModel,
    AccessSetupSessionReadModel,
    CredentialBindingReadModel,
)
from crxzipple.modules.access.application.repositories import (
    AccessActionAuditRecord,
    AccessAssetRecord,
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
    AccessReadinessSnapshotRecord,
    AccessSetupSessionRecord,
)
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsConfigProvider,
)


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class AccessQueryDegraded:
    reason: str
    missing_dependencies: tuple[str, ...] = ()

    def to_payload(self) -> JsonObject:
        return {
            "status": "degraded",
            "degraded": True,
            "degraded_reason": self.reason,
            "dependency_missing": list(self.missing_dependencies),
        }


@dataclass(frozen=True, slots=True)
class AccessQueryResult:
    payload: JsonObject
    degraded: AccessQueryDegraded | None = None

    def to_payload(self) -> JsonObject:
        if self.degraded is None:
            return {"status": "ready", "degraded": False, **self.payload}
        return {**self.degraded.to_payload(), **self.payload}


@dataclass(slots=True)
class AccessControlPlaneQueryProvider:
    governance_repository: object | None
    audit_repository: object | None = None
    settings_config_provider: AccessSettingsConfigProvider | None = None
    generated_at_factory: Any = field(
        default=lambda: datetime.now(timezone.utc),
        repr=False,
    )

    def overview(self) -> AccessQueryResult:
        records = self._records()
        if isinstance(records, AccessQueryDegraded):
            return AccessQueryResult(
                payload=self._empty_overview().to_payload(),
                degraded=records,
            )
        (
            assets,
            credentials,
            consumers,
            readiness,
            setup_sessions,
            audits,
        ) = records
        overview = AccessOverviewReadModel(
            ready=not any(not item.ready for item in readiness),
            counts=self._counts(
                assets=assets,
                credentials=credentials,
                readiness=readiness,
                setup_sessions=setup_sessions,
                audits=audits,
            ),
            assets=self._asset_list_from_records(
                assets,
                credentials=credentials,
                readiness=readiness,
            ),
            readiness=readiness,
            credential_bindings=credentials,
            consumer_bindings=consumers,
            setup_sessions=setup_sessions,
            audits=audits,
            generated_at=self._now(),
        )
        return AccessQueryResult(payload=overview.to_payload())

    def assets(self) -> AccessQueryResult:
        records = self._records()
        if isinstance(records, AccessQueryDegraded):
            return AccessQueryResult(
                payload=AccessAssetListReadModel(generated_at=self._now()).to_payload(),
                degraded=records,
            )
        assets, credentials, _consumers, readiness, _setup_sessions, _audits = (
            records
        )
        return AccessQueryResult(
            payload=self._asset_list_from_records(
                assets,
                credentials=credentials,
                readiness=readiness,
            ).to_payload(),
        )

    def asset_detail(self, asset_id: str) -> AccessQueryResult | None:
        normalized = asset_id.strip()
        records = self._records()
        if isinstance(records, AccessQueryDegraded):
            return AccessQueryResult(
                payload={
                    "asset_id": normalized,
                    "asset_kind": "unknown",
                    "display_name": normalized,
                    "governance_scope": "unknown",
                    "status": "unknown",
                    "credential_bindings": [],
                    "consumer_bindings": [],
                },
                degraded=records,
            )
        (
            assets,
            credentials,
            consumers,
            readiness,
            _setup_sessions,
            _audits,
        ) = records
        asset = next((item for item in assets if item.asset_id == normalized), None)
        if asset is None:
            return None
        detail = AccessAssetDetailReadModel(
            asset_id=asset.asset_id,
            asset_kind=asset.asset_kind,
            display_name=asset.display_name,
            governance_scope=asset.governance_scope,
            status=asset.status,
            secret_policy=asset.secret_policy,
            storage_key=asset.storage_key,
            consumer_modules=asset.consumer_modules,
            readiness_policy=asset.readiness_policy,
            rotation_policy=asset.rotation_policy,
            audit_required=asset.audit_required,
            export_policy=asset.export_policy,
            degraded_reason=asset.degraded_reason,
            readiness=self._readiness_for(readiness, "asset", asset.asset_id),
            credential_bindings=tuple(
                item for item in credentials if item.asset_id == asset.asset_id
            ),
            consumer_bindings=tuple(
                item for item in consumers if item.asset_id == asset.asset_id
            ),
            metadata=asset.metadata,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )
        return AccessQueryResult(payload=detail.to_payload())

    def consumers(self) -> AccessQueryResult:
        records = self._records()
        if isinstance(records, AccessQueryDegraded):
            return AccessQueryResult(payload={"consumers": []}, degraded=records)
        _assets, _credentials, consumers, _readiness, _setup_sessions, _audits = (
            records
        )
        return AccessQueryResult(
            payload={
                "consumers": [item.to_payload() for item in consumers],
            },
        )

    def audits(self, *, limit: int = 50, offset: int = 0) -> AccessQueryResult:
        records = self._records(limit=limit, offset=offset)
        if isinstance(records, AccessQueryDegraded):
            return AccessQueryResult(payload={"audits": []}, degraded=records)
        _assets, _credentials, _consumers, _readiness, _setup_sessions, audits = (
            records
        )
        return AccessQueryResult(
            payload={
                "audits": [item.to_payload() for item in audits],
                "limit": min(max(int(limit), 1), 200),
                "offset": max(int(offset), 0),
            },
        )

    def _records(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> (
        tuple[
            tuple[AccessAssetRecord, ...],
            tuple[CredentialBindingReadModel, ...],
            tuple[AccessConsumerBindingReadModel, ...],
            tuple[AccessReadinessReadModel, ...],
            tuple[AccessSetupSessionReadModel, ...],
            tuple[AccessAuditReadModel, ...],
        ]
        | AccessQueryDegraded
    ):
        repository = self.governance_repository
        settings_records = self._settings_config_records()
        if settings_records is None:
            return AccessQueryDegraded(
                reason="dependency missing: settings access config",
                missing_dependencies=(
                    "settings_access_config",
                ),
            )
        if repository is None:
            return AccessQueryDegraded(
                reason="dependency missing: access runtime repository",
                missing_dependencies=("access_governance_repository",),
            )
        try:
            assets, credential_records, consumer_records = settings_records
            readiness_records = tuple(_call_optional(repository, "list_readiness_snapshots"))
            setup_records = tuple(_call_optional(repository, "list_setup_sessions"))
            audit_records = self._list_audits(limit=limit, offset=offset)
        except Exception as exc:
            return AccessQueryDegraded(
                reason=f"dependency missing: access config source ({exc})",
                missing_dependencies=("access_config_source",),
            )
        return (
            assets,
            tuple(
                _credential_binding_model(item) for item in credential_records
            ),
            tuple(_consumer_binding_model(item) for item in consumer_records),
            tuple(_readiness_model(item) for item in readiness_records),
            tuple(_setup_session_model(item) for item in setup_records),
            tuple(_audit_model(item) for item in audit_records),
        )

    def _settings_config_records(
        self,
    ) -> (
        tuple[
            tuple[AccessAssetRecord, ...],
            tuple[AccessCredentialBindingRecord, ...],
            tuple[AccessConsumerBindingRecord, ...],
        ]
        | None
    ):
        if self.settings_config_provider is None:
            return None
        view = self.settings_config_provider.view()
        return (
            view.list_assets(),
            view.list_credential_bindings(),
            view.list_consumer_bindings(),
        )

    def _list_audits(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[AccessActionAuditRecord, ...]:
        if self.audit_repository is None:
            return ()
        list_recent = getattr(self.audit_repository, "list_recent", None)
        if list_recent is None:
            return ()
        return tuple(list_recent(limit=limit, offset=offset))

    def _asset_list_from_records(
        self,
        assets: tuple[AccessAssetRecord, ...],
        *,
        credentials: tuple[CredentialBindingReadModel, ...],
        readiness: tuple[AccessReadinessReadModel, ...],
    ) -> AccessAssetListReadModel:
        summaries = tuple(
            AccessAssetSummaryReadModel(
                asset_id=asset.asset_id,
                asset_kind=asset.asset_kind,
                display_name=asset.display_name,
                governance_scope=asset.governance_scope,
                status=asset.status,
                readiness=self._readiness_for(readiness, "asset", asset.asset_id),
                consumer_modules=asset.consumer_modules,
                credential_binding_count=sum(
                    1 for item in credentials if item.asset_id == asset.asset_id
                ),
                metadata=asset.metadata,
            )
            for asset in assets
        )
        return AccessAssetListReadModel(
            assets=summaries,
            counts={
                "total": len(summaries),
                "active": sum(1 for item in summaries if item.status == "active"),
                "blocked": sum(
                    1
                    for item in summaries
                    if item.readiness is not None and not item.readiness.ready
                ),
            },
            generated_at=self._now(),
        )

    def _counts(
        self,
        *,
        assets: tuple[AccessAssetRecord, ...],
        credentials: tuple[CredentialBindingReadModel, ...],
        readiness: tuple[AccessReadinessReadModel, ...],
        setup_sessions: tuple[AccessSetupSessionReadModel, ...],
        audits: tuple[AccessAuditReadModel, ...],
    ) -> JsonObject:
        return {
            "assets": len(assets),
            "credential_bindings": len(credentials),
            "readiness": len(readiness),
            "blocked": sum(1 for item in readiness if not item.ready),
            "setup_sessions": len(setup_sessions),
            "audits": len(audits),
        }

    def _empty_overview(self) -> AccessOverviewReadModel:
        return AccessOverviewReadModel(
            ready=False,
            counts={
                "assets": 0,
                "credential_bindings": 0,
                "readiness": 0,
                "blocked": 0,
                "setup_sessions": 0,
                "audits": 0,
            },
            generated_at=self._now(),
        )

    def _readiness_for(
        self,
        readiness: tuple[AccessReadinessReadModel, ...],
        target_kind: str,
        target_id: str,
    ) -> AccessReadinessReadModel | None:
        return next(
            (
                item
                for item in readiness
                if item.target_kind == target_kind and item.target_id == target_id
            ),
            None,
        )

    def _now(self) -> datetime:
        return self.generated_at_factory()


def _call_optional(repository: object, method_name: str) -> tuple[object, ...]:
    method = getattr(repository, method_name, None)
    if method is None:
        return ()
    return tuple(method())


def _credential_binding_model(
    record: AccessCredentialBindingRecord,
) -> CredentialBindingReadModel:
    return CredentialBindingReadModel(
        binding_id=record.binding_id,
        binding_kind=record.binding_kind,
        source_kind=record.source_kind,
        source_ref=record.source_ref,
        asset_id=record.asset_id,
        masked_preview=record.masked_preview,
        status=record.status,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _consumer_binding_model(
    record: AccessConsumerBindingRecord,
) -> AccessConsumerBindingReadModel:
    return AccessConsumerBindingReadModel(
        binding_id=record.binding_id,
        consumer_module=record.consumer_module,
        consumer_kind=record.consumer_kind,
        consumer_id=record.consumer_id,
        display_name=record.display_name,
        enabled=record.enabled,
        asset_id=record.asset_id,
        credential_binding_id=record.credential_binding_id,
        requirement_sets=record.requirement_sets,
        status=record.status,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _readiness_model(record: AccessReadinessSnapshotRecord) -> AccessReadinessReadModel:
    return AccessReadinessReadModel(
        target_kind=record.target_kind,
        target_id=record.target_id,
        status=record.status,
        ready=record.ready,
        reason=record.reason,
        checks=record.checks,
        setup_available=record.status != "ready",
        metadata=record.metadata,
        observed_at=record.created_at,
    )


def _setup_session_model(record: AccessSetupSessionRecord) -> AccessSetupSessionReadModel:
    return AccessSetupSessionReadModel(
        session_id=record.session_id,
        target_kind=record.target_kind,
        target_id=record.target_id,
        status=record.status,
        flow_kind=record.flow_kind,
        requested_by=record.requested_by,
        expires_at=record.expires_at,
        completed_at=record.completed_at,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _audit_model(record: AccessActionAuditRecord) -> AccessAuditReadModel:
    return AccessAuditReadModel(
        audit_id=record.audit_id,
        action_type=record.action_type,
        target_type=record.target_type,
        target_id=record.target_id,
        status=record.status,
        operator=record.operator,
        source=record.source,
        reason=record.reason,
        request_metadata=record.request_metadata,
        result=record.result,
        error=record.error,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
