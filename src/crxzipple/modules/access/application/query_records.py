from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from crxzipple.modules.access.application.read_models import (
    AccessAuditReadModel,
    AccessConsumerBindingReadModel,
    AccessOAuthAccountReadModel,
    AccessOAuthProviderReadModel,
    AccessReadinessReadModel,
    AccessSetupSessionReadModel,
    CredentialBindingReadModel,
)
from crxzipple.modules.access.application.repositories import (
    AccessAssetRecord,
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
)
from crxzipple.modules.access.application.query_record_models import (
    consumer_binding_model,
    credential_binding_model,
    merge_consumer_binding_models,
    oauth_account_model,
    oauth_provider_model,
    readiness_model,
    setup_session_model,
)
from crxzipple.modules.access.application.query_results import AccessQueryDegraded


ExternalConsumerBindingProvider = Callable[
    [],
    tuple[AccessConsumerBindingReadModel, ...],
]


@dataclass(frozen=True, slots=True)
class AccessQueryRecords:
    assets: tuple[AccessAssetRecord, ...]
    credentials: tuple[CredentialBindingReadModel, ...]
    consumers: tuple[AccessConsumerBindingReadModel, ...]
    readiness: tuple[AccessReadinessReadModel, ...]
    setup_sessions: tuple[AccessSetupSessionReadModel, ...]
    oauth_providers: tuple[AccessOAuthProviderReadModel, ...]
    oauth_accounts: tuple[AccessOAuthAccountReadModel, ...]
    audits: tuple[AccessAuditReadModel, ...] = ()


def collect_access_query_records(
    *,
    governance_repository: object | None,
    settings_config_provider: object | None,
    external_consumer_binding_provider: ExternalConsumerBindingProvider | None,
    now: datetime,
    audit_models: tuple[AccessAuditReadModel, ...] = (),
) -> AccessQueryRecords | AccessQueryDegraded:
    settings_records = _settings_config_records(settings_config_provider)
    if settings_records is None:
        return AccessQueryDegraded(
            reason="dependency missing: settings access config",
            missing_dependencies=("settings_access_config",),
        )
    repository = governance_repository
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
    except Exception as exc:
        return AccessQueryDegraded(
            reason=f"dependency missing: access config source ({exc})",
            missing_dependencies=("access_config_source",),
        )
    settings_consumers = tuple(
        consumer_binding_model(item) for item in consumer_records
    )
    consumers = merge_consumer_binding_models(
        settings_consumers,
        _external_consumer_bindings(external_consumer_binding_provider),
    )
    return AccessQueryRecords(
        assets=assets,
        credentials=tuple(
            credential_binding_model(item) for item in credential_records
        ),
        consumers=consumers,
        readiness=tuple(readiness_model(item) for item in readiness_records),
        setup_sessions=tuple(
            setup_session_model(item, now=now) for item in setup_records
        ),
        oauth_providers=tuple(
            oauth_provider_model(item) for item in oauth_provider_records
        ),
        oauth_accounts=tuple(
            oauth_account_model(item) for item in oauth_account_records
        ),
        audits=audit_models,
    )


def _settings_config_records(
    settings_config_provider: object | None,
) -> (
    tuple[
        tuple[AccessAssetRecord, ...],
        tuple[AccessCredentialBindingRecord, ...],
        tuple[AccessConsumerBindingRecord, ...],
    ]
    | None
):
    if settings_config_provider is None:
        return None
    view = settings_config_provider.view()
    return (
        view.list_assets(),
        view.list_credential_bindings(),
        view.list_consumer_bindings(),
    )


def _external_consumer_bindings(
    provider: ExternalConsumerBindingProvider | None,
) -> tuple[AccessConsumerBindingReadModel, ...]:
    if provider is None:
        return ()
    return tuple(provider())


def _call_optional(repository: object, method_name: str) -> tuple[object, ...]:
    method = getattr(repository, method_name, None)
    if method is None:
        return ()
    return tuple(method())
