from __future__ import annotations

import os
from pathlib import Path

from crxzipple.modules.access.domain import (
    AccessRequirement,
    AccessSetupAction,
    AccessSetupActionKind,
    AccessSetupFlow,
    AccessSetupFlowKind,
)


def unsupported_access_requirement_flow() -> AccessSetupFlow:
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.UNSUPPORTED,
        title="Unsupported access requirement",
        description="The access requirement is empty.",
    )


def unsupported_access_setup_flow(description: str) -> AccessSetupFlow:
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.UNSUPPORTED,
        title="Unsupported access setup",
        description=description,
    )


def invalid_environment_credential_flow() -> AccessSetupFlow:
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.UNSUPPORTED,
        title="Invalid environment credential",
        description="The env credential binding does not include a variable name.",
    )


def environment_setup_flow(env_name: str) -> AccessSetupFlow:
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.ENV,
        title=f"Configure {env_name}",
        description=(
            f"Set the {env_name} environment variable and restart the process "
            "that needs this access."
        ),
        action_label="Set environment variable",
        env_vars=(env_name,),
        actions=(
            AccessSetupAction(
                kind=AccessSetupActionKind.CONFIGURE_ENV,
                label="Set environment variable",
                description=(
                    f"Configure {env_name} in the environment of the process "
                    "that needs this access."
                ),
                env_vars=(env_name,),
                metadata={"requires_restart": True},
            ),
        ),
    )


def file_setup_flow(
    raw_path: str,
    *,
    workspace_dir: str | None,
) -> AccessSetupFlow:
    display_path = display_credential_file_path(
        raw_path,
        workspace_dir=workspace_dir,
    )
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.FILE,
        title="Create credential file",
        description=(
            "Write the credential value to the configured file path. "
            "The access resolver reads the file content at runtime."
        ),
        action_label="Create credential file",
        path=display_path,
        actions=(
            AccessSetupAction(
                kind=AccessSetupActionKind.CREATE_FILE,
                label="Create credential file",
                description="Write the credential value to this file path.",
                path=display_path,
            ),
        ),
    )


def oauth_provider_setup_flow(
    parsed: AccessRequirement,
    provider: object,
) -> AccessSetupFlow:
    authorize_url = getattr(provider, "authorization_url", None)
    callback_url = getattr(provider, "callback_url", None)
    provider_id = getattr(provider, "provider_id", parsed.provider or "")
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.OAUTH_BROWSER,
        title=f"Authorize {getattr(provider, 'display_name', parsed.provider or 'OAuth')}",
        description=(
            "Start an Access OAuth setup session, complete the provider "
            "authorization, then bind the resulting OAuth account."
        ),
        action_label="Start OAuth setup",
        authorize_url=authorize_url,
        callback_url=callback_url,
        metadata={
            "provider": provider_id,
            "scopes": list(parsed.scopes),
            "requires_setup_session": True,
        },
        actions=(
            AccessSetupAction(
                kind=AccessSetupActionKind.OPEN_URL,
                label="Open provider authorization",
                url=authorize_url,
                metadata={
                    "provider": provider_id,
                    "requires_setup_session": True,
                },
            ),
        ),
    )


def oauth_provider_not_configured_flow(parsed: AccessRequirement) -> AccessSetupFlow:
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.UNSUPPORTED,
        title="OAuth setup is not configured",
        description=(
            "This requirement needs an OAuth provider asset before access can "
            "create a browser or device-code login flow."
        ),
        metadata={
            "provider": parsed.provider or "",
            "scopes": list(parsed.scopes),
        },
    )


def inactive_credential_binding_setup_flow(
    binding_id: str,
    status: str,
) -> AccessSetupFlow:
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.UNSUPPORTED,
        title="Credential binding is not active",
        description=f"Credential binding '{binding_id}' is {status}.",
        metadata={"credential_binding_id": binding_id, "status": status},
    )


def missing_credential_source_setup_flow(binding_id: str) -> AccessSetupFlow:
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.UNSUPPORTED,
        title="Credential source is missing",
        description=f"Credential binding '{binding_id}' has no source.",
        metadata={"credential_binding_id": binding_id},
    )


def app_credential_setup_flow(
    *,
    binding_id: str,
    source_kind: str,
    source_ref: str,
) -> AccessSetupFlow:
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.MESSAGE,
        title="Prepare app credential reference",
        description=(
            f"Credential binding '{binding_id}' points at app credential "
            f"reference '{source_ref}'. Ensure the owning Access asset can "
            "resolve that reference before using it at runtime."
        ),
        metadata={
            "credential_binding_id": binding_id,
            "source_kind": source_kind,
            "source_ref": source_ref,
        },
    )


def codex_oauth_setup_flow(
    *,
    binding_id: str,
    source_ref: str,
    provider_id: str,
) -> AccessSetupFlow:
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.OAUTH_BROWSER,
        title="Authorize OpenAI Codex",
        description=(
            "Start the built-in OpenAI Codex OAuth flow, complete it in "
            "the browser, and let Access bind the OAuth account."
        ),
        action_label="Start OAuth login",
        callback_url="http://localhost:1455/auth/callback",
        metadata={
            "credential_binding_id": binding_id,
            "account_id": source_ref,
            "provider": provider_id,
            "access_action_intent": "begin_codex_oauth_login",
        },
        actions=(
            AccessSetupAction(
                kind=AccessSetupActionKind.OPEN_URL,
                label="Start OpenAI Codex OAuth",
                description=(
                    "Open the OpenAI authorization page and wait for the "
                    "local callback to complete."
                ),
                url="https://auth.openai.com/oauth/authorize",
                metadata={
                    "credential_binding_id": binding_id,
                    "account_id": source_ref,
                    "access_action_intent": "begin_codex_oauth_login",
                },
            ),
        ),
    )


def oauth_account_not_configured_flow(
    *,
    binding_id: str,
    source_ref: str,
    provider_id: str,
) -> AccessSetupFlow:
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.UNSUPPORTED,
        title="OAuth account is not configured",
        description=(
            f"OAuth account '{source_ref}' is required by credential binding "
            f"'{binding_id}', but Access has no setup flow for it yet."
        ),
        metadata={
            "credential_binding_id": binding_id,
            "account_id": source_ref,
            "provider": provider_id,
        },
    )


def unsupported_credential_source_setup_flow(
    *,
    binding_id: str,
    source_kind: str,
) -> AccessSetupFlow:
    return AccessSetupFlow(
        kind=AccessSetupFlowKind.UNSUPPORTED,
        title="Unsupported credential source",
        description=(
            f"Credential binding '{binding_id}' uses unsupported source "
            f"'{source_kind}'."
        ),
        metadata={"credential_binding_id": binding_id, "source_kind": source_kind},
    )


def oauth_provider_id_from_account_ref(account_ref: str) -> str:
    normalized = account_ref.strip()
    if ":" in normalized:
        return normalized.split(":", 1)[0].strip()
    return normalized


def display_credential_file_path(
    path_value: str,
    *,
    workspace_dir: str | None,
) -> str:
    if not path_value:
        return ""
    expanded = os.path.expandvars(os.path.expanduser(path_value))
    path = Path(expanded)
    if not path.is_absolute() and workspace_dir:
        path = Path(workspace_dir) / path
    return str(path)
