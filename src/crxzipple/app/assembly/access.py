"""Access module app assembly."""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.modules.access import AccessApplicationService
from crxzipple.modules.access.application.oauth import AccessOAuthService
from crxzipple.modules.access.application.settings_config_views import (
    AccessSettingsConfigProvider,
)
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsActionAdapter,
)
from crxzipple.modules.access.infrastructure import (
    FileBackedAccessOAuthTokenStore,
    SqlAlchemyAccessActionAuditRepository,
    SqlAlchemyAccessGovernanceRepository,
)


def access_factories(
    *,
    ensure_default_oauth_provider: bool = True,
) -> tuple[ApplicationFactory, ...]:
    """Build Access module-local services and repositories."""

    return (
        ApplicationFactory(
            key="access.services",
            provides=(
                AppKey.ACCESS_SERVICE,
                AppKey.ACCESS_GOVERNANCE_REPOSITORY,
                AppKey.ACCESS_ACTION_AUDIT_REPOSITORY,
                AppKey.ACCESS_OAUTH_TOKEN_STORE,
                AppKey.ACCESS_OAUTH_SERVICE,
            ),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.DATABASE_ENGINE,
                AppKey.DATABASE_SESSION_FACTORY,
                AppKey.EVENTS_SERVICE,
                AppKey.SETTINGS_ACTION_SERVICE,
                AppKey.SETTINGS_QUERY_SERVICE,
            ),
            build=lambda ctx: _build_access_services(
                ctx,
                ensure_default_oauth_provider=ensure_default_oauth_provider,
            ),
        ),
    )


def _build_access_services(
    ctx,
    *,
    ensure_default_oauth_provider: bool,
) -> dict[str, Any]:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    engine = ctx.require(AppKey.DATABASE_ENGINE)
    session_factory = ctx.require(AppKey.DATABASE_SESSION_FACTORY)
    events_service = ctx.require(AppKey.EVENTS_SERVICE)
    settings_action_service = ctx.require(AppKey.SETTINGS_ACTION_SERVICE)
    settings_query_service = ctx.require(AppKey.SETTINGS_QUERY_SERVICE)

    governance_repository = SqlAlchemyAccessGovernanceRepository(session_factory)
    action_audit_repository = SqlAlchemyAccessActionAuditRepository(session_factory)
    oauth_token_store = FileBackedAccessOAuthTokenStore(settings.access_state_dir)
    access_service = AccessApplicationService(
        config_view=AccessSettingsConfigProvider(
            settings_query_service,
            environment=settings.environment,
        ),
        oauth_account_repository=governance_repository,
        oauth_token_store=oauth_token_store,
        event_publisher=events_service,
    )
    oauth_service = AccessOAuthService(
        repository=governance_repository,
        token_store=oauth_token_store,
        settings_action_adapter=AccessSettingsActionAdapter(
            action_service=settings_action_service,
            query_service=settings_query_service,
            environment=settings.environment,
        ),
    )
    if ensure_default_oauth_provider and inspect(engine).has_table(
        "access_oauth_providers",
    ):
        oauth_service.ensure_default_codex_provider()

    return {
        AppKey.ACCESS_SERVICE: access_service,
        AppKey.ACCESS_GOVERNANCE_REPOSITORY: governance_repository,
        AppKey.ACCESS_ACTION_AUDIT_REPOSITORY: action_audit_repository,
        AppKey.ACCESS_OAUTH_TOKEN_STORE: oauth_token_store,
        AppKey.ACCESS_OAUTH_SERVICE: oauth_service,
    }


__all__ = ["access_factories"]
