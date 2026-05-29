"""Authorization module app assembly."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.modules.authorization.application import AuthorizationApplicationService
from crxzipple.modules.authorization.infrastructure import (
    AbacAuthorizationEvaluator,
    YamlAuthorizationPolicyLoader,
)
from crxzipple.modules.authorization.infrastructure.persistence import (
    SqlAlchemyAuthorizationAuditRepository,
    SqlAlchemyAuthorizationPolicyRepository,
    SqlAlchemyTemporaryAuthorizationGrantRepository,
)


@dataclass(frozen=True, slots=True)
class AuthorizationBootstrapConfig:
    enabled: bool = True
    policy_paths: tuple[str, ...] = ()


def authorization_factories() -> tuple[ApplicationFactory, ...]:
    """Build Authorization module-local services from settings governance."""

    return (
        ApplicationFactory(
            key="authorization.service",
            provides=(
                AppKey.AUTHORIZATION_SERVICE,
                AppKey.AUTHORIZATION_BOOTSTRAP_POLICY_COUNT,
            ),
            requires=(
                AppKey.CORE_SETTINGS,
                AppKey.DATABASE_SESSION_FACTORY,
                AppKey.SETTINGS_QUERY_SERVICE,
            ),
            build=_build_authorization_service,
        ),
    )


def _build_authorization_service(ctx) -> dict[str, Any]:
    settings = ctx.require(AppKey.CORE_SETTINGS)
    session_factory = ctx.require(AppKey.DATABASE_SESSION_FACTORY)
    settings_query_service = ctx.require(AppKey.SETTINGS_QUERY_SERVICE)
    bootstrap_config = _authorization_bootstrap_config_from_settings(
        settings_query_service,
        environment=settings.environment,
    )
    bootstrap_policies = YamlAuthorizationPolicyLoader().load_paths(
        bootstrap_config.policy_paths,
    )
    service = AuthorizationApplicationService(
        policy_repository=SqlAlchemyAuthorizationPolicyRepository(
            session_factory=session_factory,
            bootstrap_policies=bootstrap_policies,
        ),
        evaluator=AbacAuthorizationEvaluator(),
        temporary_grant_repository_factory=(
            lambda: SqlAlchemyTemporaryAuthorizationGrantRepository(session_factory)
        ),
        audit_repository=SqlAlchemyAuthorizationAuditRepository(session_factory),
        enabled=bootstrap_config.enabled,
    )
    return {
        AppKey.AUTHORIZATION_SERVICE: service,
        AppKey.AUTHORIZATION_BOOTSTRAP_POLICY_COUNT: len(bootstrap_policies),
    }


def _authorization_bootstrap_config_from_settings(
    settings_query_service: Any,
    *,
    environment: str,
) -> AuthorizationBootstrapConfig:
    try:
        resolution = settings_query_service.get_effective(environment)
    except Exception:
        return AuthorizationBootstrapConfig()
    payload = resolution.effective_value
    if not isinstance(payload, Mapping):
        return AuthorizationBootstrapConfig()
    policy_paths = _string_tuple_from_value(payload.get("authorization_policy_paths"))
    runtime_policy_path = _optional_string(payload.get("authorization_runtime_policy_path"))
    if runtime_policy_path is not None:
        policy_paths = (*policy_paths, runtime_policy_path)
    return AuthorizationBootstrapConfig(
        enabled=_bool_from_value(payload.get("authorization_enabled"), default=True),
        policy_paths=tuple(dict.fromkeys(policy_paths)),
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_tuple_from_value(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if isinstance(value, (list, tuple)):
        return tuple(text for item in value if (text := str(item).strip()))
    return ()


def _bool_from_value(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"0", "false", "no", "off"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
    return bool(value)


__all__ = ["AuthorizationBootstrapConfig", "authorization_factories"]
