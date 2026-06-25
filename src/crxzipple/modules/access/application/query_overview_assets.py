from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.access.application.read_models import (
    AccessAssetListReadModel,
    AccessAssetSummaryReadModel,
    AccessConsumerBindingReadModel,
    AccessCredentialRequirementReadModel,
    AccessOAuthAccountReadModel,
    AccessOAuthProviderReadModel,
    AccessOverviewReadModel,
    AccessReadinessReadModel,
    AccessSetupSessionReadModel,
    CredentialBindingReadModel,
)
from crxzipple.modules.access.application.repositories import AccessAssetRecord

from .query_assets import (
    consumers_for_asset,
    synthetic_asset_summaries,
    unique_strings,
)


JsonObject = dict[str, Any]


def access_asset_list_from_records(
    assets: tuple[AccessAssetRecord, ...],
    *,
    credentials: tuple[CredentialBindingReadModel, ...],
    consumers: tuple[AccessConsumerBindingReadModel, ...],
    readiness: tuple[AccessReadinessReadModel, ...],
    generated_at: datetime,
) -> AccessAssetListReadModel:
    explicit_summaries = []
    for asset in assets:
        asset_credentials = tuple(
            item for item in credentials if item.asset_id == asset.asset_id
        )
        asset_consumers = consumers_for_asset(
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
                readiness=readiness_for(readiness, "asset", asset.asset_id),
                consumer_modules=unique_strings(
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
            *synthetic_asset_summaries(
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
        generated_at=generated_at,
    )


def access_overview_counts(
    *,
    asset_count: int,
    credentials: tuple[CredentialBindingReadModel, ...],
    readiness: tuple[AccessReadinessReadModel, ...],
    credential_requirements: tuple[AccessCredentialRequirementReadModel, ...],
    setup_sessions: tuple[AccessSetupSessionReadModel, ...],
    oauth_providers: tuple[AccessOAuthProviderReadModel, ...],
    oauth_accounts: tuple[AccessOAuthAccountReadModel, ...],
    now: datetime,
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
            if item.expires_at is not None and item.expires_at <= now
        ),
        "readiness": len(readiness),
        "blocked": sum(1 for item in readiness if not item.ready),
        "setup_sessions": len(setup_sessions),
    }


def empty_access_overview(*, generated_at: datetime) -> AccessOverviewReadModel:
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
        generated_at=generated_at,
    )


def readiness_for(
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
