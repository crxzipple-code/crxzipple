from __future__ import annotations

from typing import Protocol

from crxzipple.modules.access.application.credential_requirement_rules import (
    credential_compatibility_error,
)
from crxzipple.modules.access.application.credential_resolver import CredentialResolver
from crxzipple.modules.access.domain import CredentialResolutionError


class AccessCredentialConfigView(Protocol):
    def get_credential_binding(self, binding_id: str) -> object | None: ...


def configured_credential_record(
    config_view: AccessCredentialConfigView | None,
    binding_id: str,
) -> object | None:
    if config_view is None:
        return None
    get_binding = getattr(config_view, "get_credential_binding", None)
    if not callable(get_binding):
        return None
    return get_binding(binding_id.strip())


def configured_credential_source(
    config_view: AccessCredentialConfigView | None,
    binding_id: str,
) -> str | None:
    record = configured_credential_record(config_view, binding_id)
    if record is None:
        return None
    source_kind = str(getattr(record, "source_kind", "")).strip()
    source_ref = str(getattr(record, "source_ref", "")).strip()
    status = str(getattr(record, "status", "active")).strip().lower() or "active"
    if status != "active":
        raise CredentialResolutionError(
            f"credential binding '{binding_id.strip()}' is {status}.",
        )
    if not source_kind or not source_ref:
        return None
    return configured_credential_source_from_record(record)


def resolve_configured_credential_record(
    binding_id: str,
    record: object,
    *,
    credential_resolver: CredentialResolver,
    oauth_account_repository: object | None,
    oauth_token_store: object | None,
    workspace_dir: str | None,
    allow_literal: bool,
    expected_kind: str | None = None,
) -> str:
    source_kind = str(getattr(record, "source_kind", "")).strip().lower()
    source_ref = str(getattr(record, "source_ref", "")).strip()
    status = str(getattr(record, "status", "active")).strip().lower() or "active"
    mismatch = credential_compatibility_error(
        record,
        expected_kind=expected_kind,
        binding_id=binding_id,
    )
    if mismatch is not None:
        raise CredentialResolutionError(mismatch)
    if status != "active":
        raise CredentialResolutionError(
            f"credential binding '{binding_id.strip()}' is {status}.",
        )
    if source_kind == "oauth_account":
        if not source_ref:
            raise CredentialResolutionError(
                f"credential binding '{binding_id.strip()}' has no OAuth account.",
            )
        return resolve_oauth_account_token(
            oauth_account_repository,
            oauth_token_store,
            source_ref,
        )
    if source_kind == "app_credential":
        if not source_ref:
            raise CredentialResolutionError(
                f"credential binding '{binding_id.strip()}' has no app credential reference.",
            )
        return source_ref
    binding_value = configured_credential_source_from_record(record)
    if binding_value is None:
        raise CredentialResolutionError(
            f"credential binding '{binding_id.strip()}' has no source.",
        )
    return credential_resolver.resolve(
        binding_value,
        workspace_dir=workspace_dir,
        allow_literal=allow_literal,
    )


def configured_credential_source_from_record(record: object) -> str | None:
    source_kind = str(getattr(record, "source_kind", "")).strip()
    source_ref = str(getattr(record, "source_ref", "")).strip()
    if not source_kind or not source_ref:
        return None
    if source_kind in {"env", "file"}:
        return f"{source_kind}:{source_ref}"
    if source_kind == "app_credential":
        return f"app_credential:{source_ref}"
    if source_kind == "oauth_account":
        return f"oauth_account:{source_ref}"
    return source_ref


def resolve_oauth_account_token(
    oauth_account_repository: object | None,
    oauth_token_store: object | None,
    account_id: str,
) -> str:
    if oauth_account_repository is None or oauth_token_store is None:
        raise CredentialResolutionError("OAuth account resolver is not configured.")
    try:
        from crxzipple.modules.access.application.oauth import AccessOAuthService

        return AccessOAuthService(
            repository=oauth_account_repository,
            token_store=oauth_token_store,
        ).resolve_access_token(account_id)
    except CredentialResolutionError:
        raise
    except Exception as exc:
        raise CredentialResolutionError(str(exc)) from exc


def configured_oauth_provider(
    oauth_account_repository: object | None,
    provider_id: str | None,
) -> object | None:
    if not provider_id or oauth_account_repository is None:
        return None
    get_provider = getattr(oauth_account_repository, "get_oauth_provider", None)
    if not callable(get_provider):
        return None
    provider = get_provider(provider_id.strip())
    if provider is None or getattr(provider, "status", "active") != "active":
        return None
    return provider
