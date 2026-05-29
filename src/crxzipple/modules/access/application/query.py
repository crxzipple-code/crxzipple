from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from crxzipple.modules.access.application.read_models import (
    AccessAssetDetailReadModel,
    AccessAssetListReadModel,
    AccessAssetSummaryReadModel,
    AccessAuditReadModel,
    AccessConsumerBindingReadModel,
    AccessOAuthAccountReadModel,
    AccessOAuthProviderReadModel,
    AccessCredentialRequirementReadModel,
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
    AccessOAuthAccountRecord,
    AccessOAuthProviderRecord,
    AccessReadinessSnapshotRecord,
    AccessSetupSessionRecord,
)
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsConfigProvider,
)
from crxzipple.shared.access import AccessSetupFlowHint, AccessSetupFlowKind


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
    external_consumer_binding_provider: (
        Callable[[], tuple[AccessConsumerBindingReadModel, ...]] | None
    ) = None
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
            oauth_providers,
            oauth_accounts,
            _audits,
        ) = records
        credential_requirements = self._credential_requirements_from_records(
            consumers,
            credentials=credentials,
            readiness=readiness,
            oauth_providers=oauth_providers,
        )
        asset_list = self._asset_list_from_records(
            assets,
            credentials=credentials,
            consumers=consumers,
            readiness=readiness,
        )
        overview = AccessOverviewReadModel(
            ready=not any(not item.ready for item in readiness),
            counts=self._counts(
                asset_count=len(asset_list.assets),
                credentials=credentials,
                readiness=readiness,
                credential_requirements=credential_requirements,
                setup_sessions=setup_sessions,
                oauth_providers=oauth_providers,
                oauth_accounts=oauth_accounts,
            ),
            assets=asset_list,
            readiness=readiness,
            credential_requirements=credential_requirements,
            credential_bindings=credentials,
            consumer_bindings=consumers,
            setup_sessions=setup_sessions,
            oauth_providers=oauth_providers,
            oauth_accounts=oauth_accounts,
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
        (
            assets,
            credentials,
            consumers,
            readiness,
            _setup_sessions,
            _oauth_providers,
            _oauth_accounts,
            _audits,
        ) = records
        return AccessQueryResult(
            payload=self._asset_list_from_records(
                assets,
                credentials=credentials,
                consumers=consumers,
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
            _oauth_providers,
            _oauth_accounts,
            _audits,
        ) = records
        asset = next((item for item in assets if item.asset_id == normalized), None)
        if asset is None:
            detail = _synthetic_asset_detail(
                normalized,
                credentials=credentials,
                consumers=consumers,
                readiness=readiness,
            )
            if detail is None:
                return None
            return AccessQueryResult(payload=detail.to_payload())
        asset_credentials = tuple(
            item for item in credentials if item.asset_id == asset.asset_id
        )
        asset_consumers = _consumers_for_asset(
            asset.asset_id,
            credentials=asset_credentials,
            consumers=consumers,
        )
        detail = AccessAssetDetailReadModel(
            asset_id=asset.asset_id,
            asset_kind=asset.asset_kind,
            display_name=asset.display_name,
            governance_scope=asset.governance_scope,
            status=asset.status,
            secret_policy=asset.secret_policy,
            storage_key=asset.storage_key,
            consumer_modules=_unique_strings(
                (
                    *asset.consumer_modules,
                    *tuple(item.consumer_module for item in asset_consumers),
                ),
            ),
            readiness_policy=asset.readiness_policy,
            rotation_policy=asset.rotation_policy,
            audit_required=asset.audit_required,
            export_policy=asset.export_policy,
            degraded_reason=asset.degraded_reason,
            readiness=self._readiness_for(readiness, "asset", asset.asset_id),
            credential_bindings=asset_credentials,
            consumer_bindings=asset_consumers,
            metadata=asset.metadata,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )
        return AccessQueryResult(payload=detail.to_payload())

    def consumers(self) -> AccessQueryResult:
        records = self._records()
        if isinstance(records, AccessQueryDegraded):
            return AccessQueryResult(payload={"consumers": []}, degraded=records)
        (
            _assets,
            _credentials,
            consumers,
            _readiness,
            _setup_sessions,
            _oauth_providers,
            _oauth_accounts,
            _audits,
        ) = records
        return AccessQueryResult(
            payload={
                "consumers": [item.to_payload() for item in consumers],
            },
        )

    def credential_requirements(self) -> AccessQueryResult:
        records = self._records()
        if isinstance(records, AccessQueryDegraded):
            return AccessQueryResult(
                payload={
                    "credential_requirements": [],
                    "requirements_by_consumer": {},
                    "missing_requirements": [],
                    "ready_requirements": [],
                    "oauth_requirements": [],
                },
                degraded=records,
            )
        (
            _assets,
            credentials,
            consumers,
            readiness,
            _setup_sessions,
            _oauth_providers,
            _oauth_accounts,
            _audits,
        ) = records
        requirements = self._credential_requirements_from_records(
            consumers,
            credentials=credentials,
            readiness=readiness,
            oauth_providers=_oauth_providers,
        )
        return AccessQueryResult(
            payload={
                "credential_requirements": [
                    item.to_payload() for item in requirements
                ],
                "requirements_by_consumer": _requirements_by_consumer_payload(
                    requirements,
                ),
                "missing_requirements": [
                    item.to_payload()
                    for item in requirements
                    if item.missing or not item.ready
                ],
                "ready_requirements": [
                    item.to_payload() for item in requirements if item.ready
                ],
                "oauth_requirements": [
                    item.to_payload()
                    for item in requirements
                    if item.expected_kind in {"oauth2_account", "openid_connect"}
                ],
            },
        )

    def audits(self, *, limit: int = 50, offset: int = 0) -> AccessQueryResult:
        records = self._records(limit=limit, offset=offset, include_audits=True)
        if isinstance(records, AccessQueryDegraded):
            return AccessQueryResult(payload={"audits": []}, degraded=records)
        (
            _assets,
            _credentials,
            _consumers,
            _readiness,
            _setup_sessions,
            _oauth_providers,
            _oauth_accounts,
            audits,
        ) = records
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
        include_audits: bool = False,
    ) -> (
        tuple[
            tuple[AccessAssetRecord, ...],
            tuple[CredentialBindingReadModel, ...],
            tuple[AccessConsumerBindingReadModel, ...],
            tuple[AccessReadinessReadModel, ...],
            tuple[AccessSetupSessionReadModel, ...],
            tuple[AccessOAuthProviderReadModel, ...],
            tuple[AccessOAuthAccountReadModel, ...],
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
            oauth_provider_records = tuple(
                _call_optional(repository, "list_oauth_providers"),
            )
            oauth_account_records = tuple(
                _call_optional(repository, "list_oauth_accounts"),
            )
            audit_models = (
                self._audit_models(limit=limit, offset=offset)
                if include_audits
                else ()
            )
        except Exception as exc:
            return AccessQueryDegraded(
                reason=f"dependency missing: access config source ({exc})",
                missing_dependencies=("access_config_source",),
            )
        settings_consumers = tuple(
            _consumer_binding_model(item) for item in consumer_records
        )
        consumers = _merge_consumer_binding_models(
            settings_consumers,
            self._external_consumer_bindings(),
        )
        return (
            assets,
            tuple(
                _credential_binding_model(item) for item in credential_records
            ),
            consumers,
            tuple(_readiness_model(item) for item in readiness_records),
            tuple(_setup_session_model(item, now=self._now()) for item in setup_records),
            tuple(_oauth_provider_model(item) for item in oauth_provider_records),
            tuple(_oauth_account_model(item) for item in oauth_account_records),
            audit_models,
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

    def _external_consumer_bindings(self) -> tuple[AccessConsumerBindingReadModel, ...]:
        provider = self.external_consumer_binding_provider
        if provider is None:
            return ()
        return tuple(provider())

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

    def _audit_models(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[AccessAuditReadModel, ...]:
        window = min(max(int(limit) + max(int(offset), 0), 1), 200)
        models = (
            tuple(
                _audit_model(record)
                for record in self._list_audits(limit=window, offset=0)
            )
            + self._settings_audit_models()
        )
        ordered = tuple(
            sorted(
                models,
                key=lambda item: item.created_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            ),
        )
        start = max(int(offset), 0)
        stop = start + min(max(int(limit), 1), 200)
        return ordered[start:stop]

    def _settings_audit_models(self) -> tuple[AccessAuditReadModel, ...]:
        provider = self.settings_config_provider
        query_service = getattr(provider, "query_service", None)
        if provider is None or query_service is None:
            return ()
        list_audits = getattr(query_service, "list_audits", None)
        if not callable(list_audits):
            return ()
        audits = []
        for record in list_audits():
            if getattr(record, "target_type", None) != "access-assets":
                continue
            audits.append(_settings_audit_model(record))
        return tuple(audits)

    def _asset_list_from_records(
        self,
        assets: tuple[AccessAssetRecord, ...],
        *,
        credentials: tuple[CredentialBindingReadModel, ...],
        consumers: tuple[AccessConsumerBindingReadModel, ...],
        readiness: tuple[AccessReadinessReadModel, ...],
    ) -> AccessAssetListReadModel:
        explicit_summaries = []
        for asset in assets:
            asset_credentials = tuple(
                item for item in credentials if item.asset_id == asset.asset_id
            )
            asset_consumers = _consumers_for_asset(
                asset.asset_id,
                credentials=asset_credentials,
                consumers=consumers,
            )
            explicit_summaries.append(
                AccessAssetSummaryReadModel(
                    asset_id=asset.asset_id,
                    asset_kind=asset.asset_kind,
                    display_name=asset.display_name,
                    governance_scope=asset.governance_scope,
                    status=asset.status,
                    readiness=self._readiness_for(readiness, "asset", asset.asset_id),
                    consumer_modules=_unique_strings(
                        (
                            *asset.consumer_modules,
                            *tuple(item.consumer_module for item in asset_consumers),
                        ),
                    ),
                    credential_binding_count=len(asset_credentials),
                    metadata=asset.metadata,
                ),
            )
        summaries = tuple(
            (
                *explicit_summaries,
                *_synthetic_asset_summaries(
                    assets,
                    credentials=credentials,
                    consumers=consumers,
                    readiness=readiness,
                ),
            ),
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
        asset_count: int,
        credentials: tuple[CredentialBindingReadModel, ...],
        readiness: tuple[AccessReadinessReadModel, ...],
        credential_requirements: tuple[AccessCredentialRequirementReadModel, ...],
        setup_sessions: tuple[AccessSetupSessionReadModel, ...],
        oauth_providers: tuple[AccessOAuthProviderReadModel, ...],
        oauth_accounts: tuple[AccessOAuthAccountReadModel, ...],
    ) -> JsonObject:
        missing_requirements = tuple(
            item for item in credential_requirements if item.missing or not item.ready
        )
        return {
            "assets": asset_count,
            "credential_bindings": len(credentials),
            "credential_requirements": len(credential_requirements),
            "missing_requirements": len(missing_requirements),
            "ready_requirements": sum(1 for item in credential_requirements if item.ready),
            "incompatible_requirements": sum(
                1
                for item in credential_requirements
                if item.status
                in {"credential_kind_mismatch", "credential_source_kind_mismatch"}
            ),
            "oauth_requirements": sum(
                1
                for item in credential_requirements
                if item.expected_kind in {"oauth2_account", "openid_connect"}
            ),
            "oauth_providers": len(oauth_providers),
            "oauth_accounts": len(oauth_accounts),
            "expired_oauth_accounts": sum(
                1
                for item in oauth_accounts
                if item.expires_at is not None and item.expires_at <= self._now()
            ),
            "readiness": len(readiness),
            "blocked": sum(1 for item in readiness if not item.ready),
            "setup_sessions": len(setup_sessions),
        }

    def _empty_overview(self) -> AccessOverviewReadModel:
        return AccessOverviewReadModel(
            ready=False,
            counts={
                "assets": 0,
                "credential_bindings": 0,
                "credential_requirements": 0,
                "missing_requirements": 0,
                "ready_requirements": 0,
                "incompatible_requirements": 0,
                "oauth_requirements": 0,
                "oauth_providers": 0,
                "oauth_accounts": 0,
                "expired_oauth_accounts": 0,
                "readiness": 0,
                "blocked": 0,
                "setup_sessions": 0,
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

    def _credential_requirements_from_records(
        self,
        consumers: tuple[AccessConsumerBindingReadModel, ...],
        *,
        credentials: tuple[CredentialBindingReadModel, ...],
        readiness: tuple[AccessReadinessReadModel, ...],
        oauth_providers: tuple[AccessOAuthProviderReadModel, ...],
    ) -> tuple[AccessCredentialRequirementReadModel, ...]:
        credentials_by_id = {item.binding_id: item for item in credentials}
        active_oauth_provider_ids = {
            item.provider_id for item in oauth_providers if item.status == "active"
        }
        rows: list[AccessCredentialRequirementReadModel] = []
        for consumer in consumers:
            if not consumer.requirement_sets:
                continue
            for set_index, requirement_set in enumerate(consumer.requirement_sets):
                for requirement_index, requirement in enumerate(requirement_set):
                    parsed = _parse_requirement_ref(requirement)
                    credential_binding_id = _binding_id_for_slot(
                        consumer,
                        str(parsed["slot"]),
                    )
                    binding = (
                        credentials_by_id.get(credential_binding_id)
                        if credential_binding_id
                        else None
                    )
                    ready, status, reason = _requirement_status(
                        expected_kind=parsed["expected_kind"],
                        binding=binding,
                        consumer_enabled=consumer.enabled,
                        consumer_status=consumer.status,
                    )
                    rows.append(
                        AccessCredentialRequirementReadModel(
                            requirement_id=_requirement_row_id(
                                consumer,
                                set_index=set_index,
                                requirement_index=requirement_index,
                            ),
                            consumer_module=consumer.consumer_module,
                            consumer_kind=consumer.consumer_kind,
                            consumer_id=consumer.consumer_id,
                            slot=str(parsed["slot"]),
                            expected_kind=str(parsed["expected_kind"]),
                            binding_id=credential_binding_id,
                            consumer_binding_id=consumer.binding_id,
                            display_name=consumer.display_name,
                            provider=parsed.get("provider"),
                            required=True,
                            ready=ready,
                            missing=binding is None,
                            status=status,
                            reason=reason,
                            setup_flow_hint=_setup_flow_hint_for_kind(
                                str(parsed["expected_kind"]),
                                provider=parsed.get("provider"),
                                provider_configured=(
                                    parsed.get("provider") in active_oauth_provider_ids
                                    if parsed.get("provider") is not None
                                    else False
                                ),
                            ),
                            metadata={
                                "requirement_set_index": set_index,
                                "requirement_index": requirement_index,
                            },
                            last_checked_at=_readiness_observed_at(
                                readiness,
                                target_kind="credential_binding",
                                target_id=credential_binding_id,
                            ),
                        ),
                    )
        return tuple(rows)

    def _now(self) -> datetime:
        return self.generated_at_factory()


def _synthetic_asset_summaries(
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
        asset_consumers = _consumers_for_asset(
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
                consumer_modules=_unique_strings(
                    tuple(item.consumer_module for item in asset_consumers),
                ),
                credential_binding_count=len(group),
                metadata=_synthetic_asset_metadata(asset_id, group),
            ),
        )
    return tuple(summaries)


def _synthetic_asset_detail(
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
    asset_consumers = _consumers_for_asset(
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
            "binding_kinds": _unique_strings(tuple(item.binding_kind for item in group)),
        },
        storage_key=None,
        consumer_modules=_unique_strings(
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
    source_kinds = _unique_strings(tuple(item.source_kind for item in credentials))
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


def _consumers_for_asset(
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
        "asset_id_source": "asset_id" if any(item.asset_id == asset_id for item in credentials) else "binding_id",
        "binding_ids": list(binding_ids),
        "binding_kinds": _unique_strings(tuple(item.binding_kind for item in credentials)),
        "source_kinds": _unique_strings(tuple(item.source_kind for item in credentials)),
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


def _unique_strings(values: tuple[str | None, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)


def _earliest_datetime(values: tuple[datetime | None, ...]) -> datetime | None:
    present = tuple(item for item in values if item is not None)
    return min(present) if present else None


def _latest_datetime(values: tuple[datetime | None, ...]) -> datetime | None:
    present = tuple(item for item in values if item is not None)
    return max(present) if present else None


def _call_optional(repository: object, method_name: str) -> tuple[object, ...]:
    method = getattr(repository, method_name, None)
    if method is None:
        return ()
    return tuple(method())


def _binding_id_for_slot(
    consumer: AccessConsumerBindingReadModel,
    slot: str,
) -> str | None:
    binding_id = consumer.credential_bindings.get(slot)
    if binding_id:
        return binding_id
    if consumer.credential_bindings:
        return None
    return consumer.credential_binding_id


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
        credential_bindings=record.credential_bindings,
        requirement_sets=record.requirement_sets,
        status=record.status,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _merge_consumer_binding_models(
    settings_consumers: tuple[AccessConsumerBindingReadModel, ...],
    external_consumers: tuple[AccessConsumerBindingReadModel, ...],
) -> tuple[AccessConsumerBindingReadModel, ...]:
    merged: dict[tuple[str, str], AccessConsumerBindingReadModel] = {}
    order: list[tuple[str, str]] = []
    for consumer in external_consumers:
        key = _consumer_merge_key(consumer)
        if key not in merged:
            order.append(key)
        merged[key] = consumer
    for consumer in settings_consumers:
        key = _consumer_merge_key(consumer)
        if key not in merged:
            order.append(key)
            merged[key] = consumer
            continue
        merged[key] = _overlay_settings_consumer_binding(
            owner=merged[key],
            settings=consumer,
        )
    return tuple(merged[key] for key in order)


def _consumer_merge_key(
    consumer: AccessConsumerBindingReadModel,
) -> tuple[str, str]:
    return (
        consumer.consumer_module.strip().lower(),
        consumer.consumer_id.strip(),
    )


def _overlay_settings_consumer_binding(
    *,
    owner: AccessConsumerBindingReadModel,
    settings: AccessConsumerBindingReadModel,
) -> AccessConsumerBindingReadModel:
    metadata = {
        **dict(owner.metadata),
        "settings_binding_id": settings.binding_id,
        "owner_binding_id": owner.binding_id,
        **dict(settings.metadata),
    }
    return AccessConsumerBindingReadModel(
        binding_id=settings.binding_id,
        consumer_module=owner.consumer_module or settings.consumer_module,
        consumer_kind=owner.consumer_kind or settings.consumer_kind,
        consumer_id=owner.consumer_id or settings.consumer_id,
        display_name=settings.display_name or owner.display_name,
        enabled=owner.enabled and settings.enabled,
        asset_id=settings.asset_id or owner.asset_id,
        credential_binding_id=(
            settings.credential_binding_id or owner.credential_binding_id
        ),
        credential_bindings={
            **dict(owner.credential_bindings),
            **dict(settings.credential_bindings),
        },
        requirement_sets=owner.requirement_sets or settings.requirement_sets,
        status=_merged_consumer_status(owner.status, settings.status),
        metadata=metadata,
        created_at=settings.created_at or owner.created_at,
        updated_at=settings.updated_at or owner.updated_at,
    )


def _merged_consumer_status(owner_status: str, settings_status: str) -> str:
    owner = owner_status.strip().lower()
    settings = settings_status.strip().lower()
    if owner != "active":
        return owner or "disabled"
    if settings != "active":
        return settings or "disabled"
    return "active"


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


def _setup_session_model(
    record: AccessSetupSessionRecord,
    *,
    now: datetime | None = None,
) -> AccessSetupSessionReadModel:
    status = record.status
    if (
        status == "waiting_for_user"
        and record.expires_at is not None
        and now is not None
        and record.expires_at <= now
    ):
        status = "expired"
    return AccessSetupSessionReadModel(
        session_id=record.session_id,
        target_kind=record.target_kind,
        target_id=record.target_id,
        status=status,
        flow_kind=record.flow_kind,
        requested_by=record.requested_by,
        expires_at=record.expires_at,
        completed_at=record.completed_at,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _oauth_provider_model(record: AccessOAuthProviderRecord) -> AccessOAuthProviderReadModel:
    return AccessOAuthProviderReadModel(
        provider_id=record.provider_id,
        display_name=record.display_name,
        provider_kind=record.provider_kind,
        status=record.status,
        default_scopes=record.default_scopes,
        authorization_url=record.authorization_url,
        token_url=record.token_url,
        revocation_url=record.revocation_url,
        device_code_url=record.device_code_url,
        callback_url=record.callback_url,
        callback_mode=record.callback_mode,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _oauth_account_model(record: AccessOAuthAccountRecord) -> AccessOAuthAccountReadModel:
    return AccessOAuthAccountReadModel(
        account_id=record.account_id,
        provider_id=record.provider_id,
        credential_binding_id=record.credential_binding_id,
        display_name=record.display_name,
        subject=record.subject,
        granted_scopes=record.granted_scopes,
        expires_at=record.expires_at,
        refresh_ready=record.refresh_ready,
        status=record.status,
        masked_preview=record.masked_preview,
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


def _settings_audit_model(record: object) -> AccessAuditReadModel:
    status = getattr(record, "status", "")
    return AccessAuditReadModel(
        audit_id=str(getattr(record, "id", "")),
        action_type=str(getattr(record, "action_type", "")),
        target_type=str(getattr(record, "target_type", "")),
        target_id=getattr(record, "target_id", None),
        status=str(getattr(status, "value", status)),
        operator=getattr(record, "actor", None),
        source="settings.access_config",
        reason=str(getattr(record, "reason", "")),
        request_metadata=dict(getattr(record, "request_metadata", {}) or {}),
        result=(
            dict(getattr(record, "result", {}) or {})
            if getattr(record, "result", None) is not None
            else None
        ),
        error=(
            dict(getattr(record, "error", {}) or {})
            if getattr(record, "error", None) is not None
            else None
        ),
        created_at=getattr(record, "created_at", None),
        updated_at=getattr(record, "updated_at", None),
    )


def _parse_requirement_ref(
    value: str,
    *,
    fallback_kind: str | None = None,
) -> JsonObject:
    normalized = str(value).strip()
    provider: str | None = None
    kind_source = normalized
    if ":" in normalized and not normalized.startswith(("env:", "file:", "literal:")):
        possible_provider, rest = normalized.split(":", 1)
        if possible_provider.strip() and "(" in rest:
            provider = possible_provider.strip()
            kind_source = rest
    expected_kind = _expected_kind_from_text(kind_source, fallback_kind=fallback_kind)
    slot = _slot_from_text(kind_source, expected_kind=expected_kind)
    return {
        "provider": provider,
        "expected_kind": expected_kind,
        "slot": slot,
    }


def _expected_kind_from_text(
    value: str,
    *,
    fallback_kind: str | None,
) -> str:
    normalized = value.strip().lower()
    candidates = {
        "api_key": ("api_key", "apikey", "x-api-key"),
        "bearer_token": ("bearer", "bearer_token", "access_token"),
        "basic": ("basic", "username", "password"),
        "oauth2_account": ("oauth2", "oauth"),
        "openid_connect": ("openid", "oidc"),
        "app_secret": ("app_secret", "client_secret"),
        "webhook_secret": ("webhook_secret", "webhook"),
        "certificate": ("certificate", "cert", "pem"),
    }
    for kind, markers in candidates.items():
        if any(marker in normalized for marker in markers):
            return kind
    if fallback_kind:
        return fallback_kind.strip().lower() or "api_key"
    return "api_key"


def _slot_from_text(value: str, *, expected_kind: str) -> str:
    normalized = value.strip()
    if "(" in normalized:
        prefix = normalized.split("(", 1)[0].strip().lower()
        inside = normalized.rsplit("(", 1)[1].rsplit(")", 1)[0].strip()
        if inside and not inside.startswith(("env:", "file:", "literal:", "inline:")):
            return _safe_slot(inside)
        if prefix:
            return _safe_slot(prefix)
    return _safe_slot(expected_kind)


def _safe_slot(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"_", "-"} else "_"
        for char in value.strip().lower()
    ).strip("_")
    return normalized or "credential"


def _requirement_status(
    *,
    expected_kind: str,
    binding: CredentialBindingReadModel | None,
    consumer_enabled: bool,
    consumer_status: str,
) -> tuple[bool, str, str | None]:
    if not consumer_enabled or consumer_status != "active":
        return False, "disabled", "consumer binding is disabled"
    if binding is None:
        return False, "missing", "credential binding is missing"
    if binding.status != "active":
        return False, binding.status, "credential binding is not active"
    binding_kind = binding.binding_kind.strip().lower()
    if binding_kind != expected_kind:
        return (
            False,
            "credential_kind_mismatch",
            "credential binding kind does not match requirement",
        )
    source_kind = binding.source_kind.strip().lower()
    if source_kind == "oauth_account" and binding_kind not in {
        "oauth2_account",
        "openid_connect",
    }:
        return (
            False,
            "credential_source_kind_mismatch",
            "oauth_account source can only satisfy OAuth or OpenID Connect credentials",
        )
    if binding_kind in {"oauth2_account", "openid_connect"} and source_kind != "oauth_account":
        return (
            False,
            "credential_source_kind_mismatch",
            "OAuth credential bindings must use an oauth_account source",
        )
    return True, "ready", None


def _setup_flow_hint_for_kind(
    expected_kind: str,
    *,
    provider: object,
    provider_configured: bool = False,
) -> AccessSetupFlowHint:
    if expected_kind in {"oauth2_account", "openid_connect"}:
        if provider_configured:
            return AccessSetupFlowHint(
                flow_kind=AccessSetupFlowKind.BROWSER_OAUTH,
                provider=str(provider).strip() if provider else None,
                metadata={
                    "setup_provider_missing": False,
                    "requires_setup_session": True,
                    "reason": "access_oauth_provider_configured",
                },
            )
        return AccessSetupFlowHint(
            flow_kind=AccessSetupFlowKind.MANUAL,
            provider=str(provider).strip() if provider else None,
            metadata={
                "setup_provider_missing": True,
                "expected_flow_kind": str(AccessSetupFlowKind.BROWSER_OAUTH),
                "reason": "access_oauth_provider_not_configured",
            },
        )
    return AccessSetupFlowHint(flow_kind=AccessSetupFlowKind.MANUAL)


def _requirement_row_id(
    consumer: AccessConsumerBindingReadModel,
    *,
    set_index: int,
    requirement_index: int,
) -> str:
    return ":".join(
        (
            "credential_requirement",
            consumer.consumer_module,
            consumer.consumer_kind,
            consumer.consumer_id,
            str(set_index),
            str(requirement_index),
        ),
    )


def _readiness_observed_at(
    readiness: tuple[AccessReadinessReadModel, ...],
    *,
    target_kind: str,
    target_id: str | None,
) -> datetime | None:
    if target_id is None:
        return None
    match = next(
        (
            item
            for item in readiness
            if item.target_kind == target_kind and item.target_id == target_id
        ),
        None,
    )
    return match.observed_at if match is not None else None


def _requirements_by_consumer_payload(
    requirements: tuple[AccessCredentialRequirementReadModel, ...],
) -> JsonObject:
    grouped: dict[str, list[JsonObject]] = {}
    for requirement in requirements:
        key = ":".join(
            (
                requirement.consumer_module,
                requirement.consumer_kind,
                requirement.consumer_id,
            ),
        )
        grouped.setdefault(key, []).append(requirement.to_payload())
    return grouped
