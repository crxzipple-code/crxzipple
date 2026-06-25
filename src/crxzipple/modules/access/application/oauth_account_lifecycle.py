from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.access.application.repositories import (
    AccessOAuthAccountRecord,
    AccessOAuthProviderRecord,
)
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsActionAdapter,
)

from .oauth_account_records import (
    oauth_account_binding_request,
    oauth_account_status_record,
    oauth_stored_account_record,
    resolved_oauth_account_id,
)
from .oauth_contracts import (
    AccessOAuthAccountResult,
    AccessOAuthRepository,
    AccessOAuthTokenStore,
)
from .oauth_token_client import AccessOAuthTokenClient
from .oauth_token_payloads import required_text


def store_oauth_account_from_token_payload(
    *,
    repository: AccessOAuthRepository,
    token_store: AccessOAuthTokenStore,
    settings_action_adapter: AccessSettingsActionAdapter | None,
    provider: AccessOAuthProviderRecord,
    token_payload: Mapping[str, Any],
    account_id: str | None,
    credential_binding_id: str | None,
    metadata: Mapping[str, Any],
    now: Any,
) -> AccessOAuthAccountResult:
    resolved_account_id = resolved_oauth_account_id(
        provider=provider,
        token_payload=token_payload,
        account_id=account_id,
    )
    storage_key = token_store.storage_key_for_account(resolved_account_id)
    stored = oauth_stored_account_record(
        provider=provider,
        token_payload=token_payload,
        account_id=account_id,
        credential_binding_id=credential_binding_id,
        storage_key=storage_key,
        metadata=metadata,
        now=now,
    )
    token_store.write_token(storage_key, stored.token_document)
    account = repository.upsert_oauth_account(stored.account)
    register_oauth_account_binding(
        settings_action_adapter=settings_action_adapter,
        account=account,
        provider=provider,
    )
    return AccessOAuthAccountResult(
        account=account,
        credential_binding_id=stored.credential_binding_id,
        provider=provider,
    )


def register_oauth_account_binding(
    *,
    settings_action_adapter: AccessSettingsActionAdapter | None,
    account: AccessOAuthAccountRecord,
    provider: AccessOAuthProviderRecord,
) -> None:
    if settings_action_adapter is None or not account.credential_binding_id:
        return
    request = oauth_account_binding_request(account, provider)
    settings_action_adapter.execute_config_action(request)


def revoke_and_update_oauth_account_status(
    *,
    repository: AccessOAuthRepository,
    token_store: AccessOAuthTokenStore,
    token_client: AccessOAuthTokenClient,
    account: AccessOAuthAccountRecord,
) -> AccessOAuthAccountRecord:
    if not account.storage_key:
        updated = oauth_account_status_record(account, status="revoked")
        return repository.upsert_oauth_account(updated)
    with token_store.token_lock(account.storage_key):
        refreshed = _existing_account(repository, account.account_id)
        revoke_oauth_account_token(
            repository=repository,
            token_store=token_store,
            token_client=token_client,
            account=refreshed,
        )
        updated = oauth_account_status_record(refreshed, status="revoked")
        token_store.delete_token(account.storage_key)
        return repository.upsert_oauth_account(updated)


def revoke_oauth_account_token(
    *,
    repository: AccessOAuthRepository,
    token_store: AccessOAuthTokenStore,
    token_client: AccessOAuthTokenClient,
    account: AccessOAuthAccountRecord,
) -> None:
    if not account.storage_key:
        return
    provider = repository.get_oauth_provider(account.provider_id)
    if provider is None or not provider.revocation_url:
        return
    token = token_store.read_token(account.storage_key)
    token_client.revoke_token(provider, token)


def _existing_account(
    repository: AccessOAuthRepository,
    account_id: str,
) -> AccessOAuthAccountRecord:
    account = repository.get_oauth_account(required_text(account_id, "OAuth account id"))
    if account is None:
        raise LookupError(f"OAuth account '{account_id}' was not found.")
    return account
