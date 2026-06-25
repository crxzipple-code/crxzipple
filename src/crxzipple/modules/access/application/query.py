from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.access.application.read_models import (
    AccessAssetDetailReadModel,
    AccessAssetListReadModel,
    AccessOverviewReadModel,
)
from crxzipple.modules.access.application.settings_config_views import (
    AccessSettingsConfigProvider,
)
from crxzipple.modules.access.application.query_audits import (
    audit_models as _audit_models,
)
from crxzipple.modules.access.application.query_results import (
    AccessQueryDegraded,
    AccessQueryResult,
)
from crxzipple.modules.access.application.query_assets import (
    consumers_for_asset as _consumers_for_asset,
    synthetic_asset_detail as _synthetic_asset_detail,
    unique_strings as _unique_strings,
)
from crxzipple.modules.access.application.query_overview_assets import (
    access_asset_list_from_records as _access_asset_list_from_records,
    access_overview_counts as _access_overview_counts,
    empty_access_overview as _empty_access_overview,
    readiness_for as _readiness_for,
)
from crxzipple.modules.access.application.query_records import (
    AccessQueryRecords,
    ExternalConsumerBindingProvider,
    collect_access_query_records as _collect_access_query_records,
)
from crxzipple.modules.access.application.query_requirements import (
    credential_requirements_from_records as _credential_requirements_from_records,
    requirements_by_consumer_payload as _requirements_by_consumer_payload,
)


@dataclass(slots=True)
class AccessControlPlaneQueryProvider:
    governance_repository: object | None
    audit_repository: object | None = None
    settings_config_provider: AccessSettingsConfigProvider | None = None
    external_consumer_binding_provider: ExternalConsumerBindingProvider | None = None
    generated_at_factory: Any = field(
        default=lambda: datetime.now(timezone.utc),
        repr=False,
    )

    def overview(self) -> AccessQueryResult:
        records = self._records()
        if isinstance(records, AccessQueryDegraded):
            return AccessQueryResult(
                payload=_empty_access_overview(generated_at=self._now()).to_payload(),
                degraded=records,
            )
        credential_requirements = _credential_requirements_from_records(
            records.consumers,
            credentials=records.credentials,
            readiness=records.readiness,
            oauth_providers=records.oauth_providers,
        )
        asset_list = _access_asset_list_from_records(
            records.assets,
            credentials=records.credentials,
            consumers=records.consumers,
            readiness=records.readiness,
            generated_at=self._now(),
        )
        overview = AccessOverviewReadModel(
            ready=not any(not item.ready for item in records.readiness),
            counts=_access_overview_counts(
                asset_count=len(asset_list.assets),
                credentials=records.credentials,
                readiness=records.readiness,
                credential_requirements=credential_requirements,
                setup_sessions=records.setup_sessions,
                oauth_providers=records.oauth_providers,
                oauth_accounts=records.oauth_accounts,
                now=self._now(),
            ),
            assets=asset_list,
            readiness=records.readiness,
            credential_requirements=credential_requirements,
            credential_bindings=records.credentials,
            consumer_bindings=records.consumers,
            setup_sessions=records.setup_sessions,
            oauth_providers=records.oauth_providers,
            oauth_accounts=records.oauth_accounts,
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
        return AccessQueryResult(
            payload=_access_asset_list_from_records(
                records.assets,
                credentials=records.credentials,
                consumers=records.consumers,
                readiness=records.readiness,
                generated_at=self._now(),
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
        asset = next(
            (item for item in records.assets if item.asset_id == normalized),
            None,
        )
        if asset is None:
            detail = _synthetic_asset_detail(
                normalized,
                credentials=records.credentials,
                consumers=records.consumers,
                readiness=records.readiness,
            )
            if detail is None:
                return None
            return AccessQueryResult(payload=detail.to_payload())
        asset_credentials = tuple(
            item for item in records.credentials if item.asset_id == asset.asset_id
        )
        asset_consumers = _consumers_for_asset(
            asset.asset_id,
            credentials=asset_credentials,
            consumers=records.consumers,
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
            readiness=_readiness_for(records.readiness, "asset", asset.asset_id),
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
        return AccessQueryResult(
            payload={
                "consumers": [item.to_payload() for item in records.consumers],
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
        requirements = _credential_requirements_from_records(
            records.consumers,
            credentials=records.credentials,
            readiness=records.readiness,
            oauth_providers=records.oauth_providers,
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
        return AccessQueryResult(
            payload={
                "audits": [item.to_payload() for item in records.audits],
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
    ) -> AccessQueryRecords | AccessQueryDegraded:
        audits = (
            _audit_models(
                self.audit_repository,
                self.settings_config_provider,
                limit=limit,
                offset=offset,
            )
            if include_audits
            else ()
        )
        return _collect_access_query_records(
            governance_repository=self.governance_repository,
            settings_config_provider=self.settings_config_provider,
            external_consumer_binding_provider=self.external_consumer_binding_provider,
            now=self._now(),
            audit_models=audits,
        )

    def _now(self) -> datetime:
        return self.generated_at_factory()
