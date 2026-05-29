from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Mapping, Protocol

from crxzipple.modules.access.domain import (
    AccessReadinessStatus,
    AccessRequirement,
    AccessRequirementReadiness,
    AccessSetupAction,
    AccessSetupActionKind,
    AccessSetupFlow,
    AccessSetupFlowKind,
    CredentialResolutionError,
)
from crxzipple.modules.access.application.events import (
    ACCESS_CREDENTIAL_LEASE_DENIED_EVENT,
    ACCESS_CREDENTIAL_LEASE_GRANTED_EVENT,
    ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT,
    ACCESS_CREDENTIAL_RESOLVE_REQUESTED_EVENT,
    ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT,
    AccessEventPublisher,
    publish_access_event,
)
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessResolvedCredential,
    CredentialBindingRef,
)


_OAUTH_BINDING_KINDS = frozenset({"oauth2_account", "openid_connect"})
_KNOWN_BINDING_KINDS = frozenset(
    {
        "api_key",
        "bearer_token",
        "basic",
        "oauth2_account",
        "openid_connect",
        "app_secret",
        "webhook_secret",
        "certificate",
    },
)


class AccessCredentialConfigView(Protocol):
    def get_credential_binding(self, binding_id: str) -> object | None: ...


@dataclass(slots=True)
class CredentialResolver:
    def resolve(
        self,
        binding: str,
        *,
        workspace_dir: str | None = None,
        allow_literal: bool = False,
    ) -> str:
        normalized = binding.strip()
        if not normalized:
            raise CredentialResolutionError("credential binding cannot be empty.")
        if normalized.startswith("env:"):
            return self._resolve_env(normalized.removeprefix("env:"))
        if normalized.startswith("file:"):
            return self._resolve_file(
                normalized.removeprefix("file:"),
                workspace_dir=workspace_dir,
            )
        if allow_literal:
            return normalized
        raise CredentialResolutionError(
            f"unsupported credential binding source '{normalized}'.",
        )

    def is_ready(
        self,
        binding: str,
        *,
        workspace_dir: str | None = None,
        allow_literal: bool = False,
    ) -> bool:
        try:
            self.resolve(
                binding,
                workspace_dir=workspace_dir,
                allow_literal=allow_literal,
            )
        except CredentialResolutionError:
            return False
        return True

    def _resolve_env(self, env_name: str) -> str:
        normalized = env_name.strip()
        if not normalized:
            raise CredentialResolutionError("env credential binding has no variable name.")
        value = os.environ.get(normalized)
        if value is None or not value.strip():
            raise CredentialResolutionError(
                f"environment variable '{normalized}' is not configured.",
            )
        return value

    def _resolve_file(
        self,
        path_value: str,
        *,
        workspace_dir: str | None,
    ) -> str:
        normalized = path_value.strip()
        if not normalized:
            raise CredentialResolutionError("file credential binding has no path.")
        expanded = os.path.expandvars(os.path.expanduser(normalized))
        path = Path(expanded)
        if not path.is_absolute():
            if not workspace_dir:
                raise CredentialResolutionError(
                    f"relative credential file '{normalized}' requires a workspace.",
                )
            path = Path(workspace_dir) / path
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise CredentialResolutionError(
                f"credential file '{path}' could not be read.",
            ) from exc
        if not value:
            raise CredentialResolutionError(f"credential file '{path}' is empty.")
        return value


@dataclass(slots=True)
class AccessApplicationService:
    credential_resolver: CredentialResolver = field(default_factory=CredentialResolver)
    ready_auth_requirements: tuple[str, ...] = ()
    config_view: AccessCredentialConfigView | None = None
    oauth_account_repository: object | None = None
    oauth_token_store: object | None = None
    event_publisher: AccessEventPublisher | None = None

    def check_requirement(
        self,
        requirement: str,
        *,
        workspace_dir: str | None = None,
    ) -> AccessRequirementReadiness:
        parsed = parse_access_requirement(requirement)
        normalized = parsed.raw
        if not normalized:
            return AccessRequirementReadiness(
                requirement=parsed,
                status=AccessReadinessStatus.UNSUPPORTED,
                reason="requirement is empty",
                setup_flow=AccessSetupFlow(
                    kind=AccessSetupFlowKind.UNSUPPORTED,
                    title="Unsupported access requirement",
                    description="The access requirement is empty.",
                ),
            )
        if normalized in self._ready_auth_requirement_set():
            return AccessRequirementReadiness(
                requirement=parsed,
                status=AccessReadinessStatus.READY,
                reason="requirement is marked ready by the access registry",
            )
        configured_record = self._configured_credential_record(normalized)
        if configured_record is not None:
            return self.check_credential_binding(
                normalized,
                workspace_dir=workspace_dir,
                requirement=parsed,
            )
        if is_credential_binding(normalized):
            return self.check_credential_binding(
                normalized,
                workspace_dir=workspace_dir,
                requirement=parsed,
            )
        if parsed.kind in {"api_key", "bearer", "basic", "credential"}:
            binding = _single_scope_binding(parsed)
            if binding is not None:
                return self.check_credential_binding(
                    binding,
                    workspace_dir=workspace_dir,
                    requirement=parsed,
                )
            return AccessRequirementReadiness(
                requirement=parsed,
                status=AccessReadinessStatus.SETUP_NEEDED,
                reason="credential requirement does not declare a binding",
                setup_flow=self.begin_setup(normalized, workspace_dir=workspace_dir),
            )
        if parsed.kind in {"oauth_connector", "oauth", "openid_connector"}:
            return AccessRequirementReadiness(
                requirement=parsed,
                status=AccessReadinessStatus.SETUP_NEEDED,
                reason="oauth connector setup is not configured yet",
                setup_flow=self.begin_setup(normalized, workspace_dir=workspace_dir),
            )
        return AccessRequirementReadiness(
            requirement=parsed,
            status=AccessReadinessStatus.UNSUPPORTED,
            reason="access requirement kind is not supported yet",
            setup_flow=self.begin_setup(normalized, workspace_dir=workspace_dir),
        )

    def check_requirements(
        self,
        requirements: tuple[str, ...],
        *,
        workspace_dir: str | None = None,
    ) -> tuple[AccessRequirementReadiness, ...]:
        return tuple(
            self.check_requirement(requirement, workspace_dir=workspace_dir)
            for requirement in requirements
        )

    def list_ready_auth_requirements(
        self,
        *,
        requirements: tuple[str, ...] = (),
        workspace_dir: str | None = None,
    ) -> tuple[str, ...]:
        if requirements:
            return tuple(
                readiness.requirement.raw
                for readiness in self.check_requirements(
                    requirements,
                    workspace_dir=workspace_dir,
                )
                if readiness.ready
            )
        return tuple(sorted(self._ready_auth_requirement_set()))

    def check_credential_binding(
        self,
        binding: str,
        *,
        workspace_dir: str | None = None,
        allow_literal: bool = False,
        requirement: AccessRequirement | None = None,
        expected_kind: str | None = None,
    ) -> AccessRequirementReadiness:
        parsed = requirement or parse_access_requirement(binding)
        expected_binding_kind = _expected_kind_for_requirement(
            parsed,
            explicit=expected_kind,
        )
        normalized = binding.strip()
        setup_target = normalized
        configured_record_found = False
        try:
            record = self._configured_credential_record(normalized)
            if record is not None:
                configured_record_found = True
                mismatch = _credential_compatibility_error(
                    record,
                    expected_kind=expected_binding_kind,
                    binding_id=normalized,
                )
                if mismatch is not None:
                    return AccessRequirementReadiness(
                        requirement=parsed,
                        status=_mismatch_readiness_status(mismatch),
                        reason=mismatch,
                        setup_flow=self.begin_setup(
                            setup_target,
                            workspace_dir=workspace_dir,
                        ),
                    )
                self._resolve_configured_credential_record(
                    normalized,
                    record,
                    workspace_dir=workspace_dir,
                    allow_literal=allow_literal,
                    expected_kind=expected_binding_kind,
                )
            else:
                binding_value = self._configured_credential_source(binding) or binding
                setup_target = binding_value
                self.credential_resolver.resolve(
                    binding_value,
                    workspace_dir=workspace_dir,
                    allow_literal=allow_literal,
                )
        except CredentialResolutionError as exc:
            unsupported = (
                normalized
                and not configured_record_found
                and not is_credential_binding(normalized)
                and not allow_literal
            )
            return AccessRequirementReadiness(
                requirement=parsed,
                status=(
                    AccessReadinessStatus.UNSUPPORTED
                    if unsupported
                    else AccessReadinessStatus.SETUP_NEEDED
                ),
                reason=str(exc),
                setup_flow=self.begin_setup(setup_target, workspace_dir=workspace_dir),
            )
        return AccessRequirementReadiness(
            requirement=parsed,
            status=AccessReadinessStatus.READY,
            reason=(
                "inline credential literal is available"
                if allow_literal
                and not is_credential_binding(binding.strip())
                else "credential binding resolved successfully"
            ),
        )

    def resolve_credential(
        self,
        binding: str | CredentialBindingRef,
        *,
        workspace_dir: str | None = None,
        allow_literal: bool = False,
        consumer: AccessConsumerRef | None = None,
        trace_context: Mapping[str, object] | None = None,
        expected_kind: str | None = None,
    ) -> str:
        expected_binding_kind = _expected_kind_from_binding_ref(
            binding,
            explicit=expected_kind,
        )
        binding_value = (
            binding.source_ref if isinstance(binding, CredentialBindingRef) else binding
        )
        event_target_id = _event_binding_id(binding_value)
        requested_payload = _credential_resolution_event_payload(
            binding_id=event_target_id,
            expected_kind=expected_binding_kind,
            consumer=consumer,
            allow_literal=allow_literal,
        )
        publish_access_event(
            self.event_publisher,
            ACCESS_CREDENTIAL_RESOLVE_REQUESTED_EVENT,
            status="requested",
            target_id=event_target_id,
            payload=requested_payload,
            trace_context=trace_context,
        )
        try:
            record = self._configured_credential_record(binding_value)
            if record is not None:
                credential = self._resolve_configured_credential_record(
                    binding_value,
                    record,
                    workspace_dir=workspace_dir,
                    allow_literal=allow_literal,
                    expected_kind=expected_binding_kind,
                )
                audit_context = _credential_record_audit_context(
                    record,
                    binding_id=binding_value,
                    consumer=consumer,
                    trace_context=trace_context,
                )
                resolved = AccessResolvedCredential(
                    credential,
                    audit_context=audit_context,
                )
            else:
                configured_binding = self._configured_credential_source(binding_value)
                if configured_binding is not None:
                    binding_value = configured_binding
                credential = self.credential_resolver.resolve(
                    binding_value,
                    workspace_dir=workspace_dir,
                    allow_literal=allow_literal,
                )
                audit_context = _direct_credential_audit_context(
                    binding_value,
                    consumer=consumer,
                    trace_context=trace_context,
                    allow_literal=allow_literal,
                )
                resolved = AccessResolvedCredential(
                    credential,
                    audit_context=audit_context,
                )
        except CredentialResolutionError as exc:
            denied_payload = {**requested_payload, "reason": str(exc)}
            publish_access_event(
                self.event_publisher,
                ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT,
                status="failed",
                level="error",
                target_id=event_target_id,
                payload=denied_payload,
                trace_context=trace_context,
            )
            publish_access_event(
                self.event_publisher,
                ACCESS_CREDENTIAL_LEASE_DENIED_EVENT,
                status="denied",
                level="warning",
                target_id=event_target_id,
                payload=denied_payload,
                trace_context=trace_context,
            )
            raise
        success_payload = {
            **requested_payload,
            "audit_context": dict(resolved.audit_context),
        }
        publish_access_event(
            self.event_publisher,
            ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT,
            status="succeeded",
            target_id=event_target_id,
            payload=success_payload,
            trace_context=trace_context,
        )
        publish_access_event(
            self.event_publisher,
            ACCESS_CREDENTIAL_LEASE_GRANTED_EVENT,
            status="granted",
            target_id=event_target_id,
            payload=success_payload,
            trace_context=trace_context,
        )
        return resolved

    def describe_credential_binding(self, binding_id: str) -> Mapping[str, object] | None:
        record = self._configured_credential_record(binding_id)
        if record is None:
            return None
        return {
            "binding_id": getattr(record, "binding_id", binding_id),
            "binding_kind": getattr(record, "binding_kind", None),
            "source_kind": getattr(record, "source_kind", None),
            "asset_id": getattr(record, "asset_id", None),
            "status": getattr(record, "status", None),
            "masked_preview": _safe_masked_preview(
                getattr(record, "source_kind", None),
                getattr(record, "masked_preview", None),
            ),
            "source_ref": _safe_source_ref(
                getattr(record, "source_kind", None),
                getattr(record, "source_ref", None),
            ),
            "source_metadata": _source_metadata(
                getattr(record, "source_kind", None),
                getattr(record, "source_ref", None),
            ),
        }

    def begin_setup(
        self,
        requirement_or_binding: str,
        *,
        workspace_dir: str | None = None,
    ) -> AccessSetupFlow:
        normalized = requirement_or_binding.strip()
        if not normalized:
            return AccessSetupFlow(
                kind=AccessSetupFlowKind.UNSUPPORTED,
                title="Unsupported access setup",
                description="The access requirement is empty.",
            )

        configured_record = self._configured_credential_record(normalized)
        if configured_record is not None:
            return self._configured_credential_setup_flow(
                normalized,
                configured_record,
                workspace_dir=workspace_dir,
            )

        if normalized.startswith("env:"):
            env_name = normalized.removeprefix("env:").strip()
            if not env_name:
                return AccessSetupFlow(
                    kind=AccessSetupFlowKind.UNSUPPORTED,
                    title="Invalid environment credential",
                    description="The env credential binding does not include a variable name.",
                )
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

        if normalized.startswith("file:"):
            raw_path = normalized.removeprefix("file:").strip()
            display_path = _display_credential_file_path(
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

        parsed = parse_access_requirement(normalized)
        if parsed.kind in {"oauth_connector", "oauth", "openid_connector"}:
            provider = self._configured_oauth_provider(parsed.provider)
            if provider is not None:
                authorize_url = getattr(provider, "authorization_url", None)
                callback_url = getattr(provider, "callback_url", None)
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
                        "provider": getattr(provider, "provider_id", parsed.provider or ""),
                        "scopes": list(parsed.scopes),
                        "requires_setup_session": True,
                    },
                    actions=(
                        AccessSetupAction(
                            kind=AccessSetupActionKind.OPEN_URL,
                            label="Open provider authorization",
                            url=authorize_url,
                            metadata={
                                "provider": getattr(
                                    provider,
                                    "provider_id",
                                    parsed.provider or "",
                                ),
                                "requires_setup_session": True,
                            },
                        ),
                    ),
                )
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

        return AccessSetupFlow(
            kind=AccessSetupFlowKind.UNSUPPORTED,
            title="Unsupported access setup",
            description=f"Access does not know how to set up '{normalized}' yet.",
        )

    def _configured_credential_setup_flow(
        self,
        binding_id: str,
        record: object,
        *,
        workspace_dir: str | None,
    ) -> AccessSetupFlow:
        source_kind = str(getattr(record, "source_kind", "")).strip().lower()
        source_ref = str(getattr(record, "source_ref", "")).strip()
        status = str(getattr(record, "status", "active")).strip().lower() or "active"
        if status != "active":
            return AccessSetupFlow(
                kind=AccessSetupFlowKind.UNSUPPORTED,
                title="Credential binding is not active",
                description=f"Credential binding '{binding_id}' is {status}.",
                metadata={"credential_binding_id": binding_id, "status": status},
            )
        if not source_kind or not source_ref:
            return AccessSetupFlow(
                kind=AccessSetupFlowKind.UNSUPPORTED,
                title="Credential source is missing",
                description=f"Credential binding '{binding_id}' has no source.",
                metadata={"credential_binding_id": binding_id},
            )
        if source_kind in {"env", "file"}:
            return self.begin_setup(
                f"{source_kind}:{source_ref}",
                workspace_dir=workspace_dir,
            )
        if source_kind == "app_credential":
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
        if source_kind == "oauth_account":
            provider_id = _oauth_provider_id_from_account_ref(source_ref)
            if (
                provider_id == "openai-codex"
                or binding_id.strip() == "codex-oauth-default"
            ):
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
            provider = self._configured_oauth_provider(provider_id)
            if provider is not None and getattr(provider, "authorization_url", None):
                return self.begin_setup(
                    f"{provider_id}:oauth",
                    workspace_dir=workspace_dir,
                )
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
        return AccessSetupFlow(
            kind=AccessSetupFlowKind.UNSUPPORTED,
            title="Unsupported credential source",
            description=(
                f"Credential binding '{binding_id}' uses unsupported source "
                f"'{source_kind}'."
            ),
            metadata={"credential_binding_id": binding_id, "source_kind": source_kind},
        )

    def _ready_auth_requirement_set(self) -> set[str]:
        env_values = os.environ.get("CRXZIPPLE_READY_AUTH_REQUIREMENTS", "")
        return {
            item.strip()
            for item in (*self.ready_auth_requirements, *env_values.split(","))
            if item is not None and item.strip()
        }

    def _configured_credential_source(self, binding_id: str) -> str | None:
        record = self._configured_credential_record(binding_id)
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
        if source_kind in {"env", "file"}:
            return f"{source_kind}:{source_ref}"
        if source_kind == "app_credential":
            return f"app_credential:{source_ref}"
        if source_kind == "oauth_account":
            return f"oauth_account:{source_ref}"
        return source_ref

    def _resolve_configured_credential_record(
        self,
        binding_id: str,
        record: object,
        *,
        workspace_dir: str | None,
        allow_literal: bool,
        expected_kind: str | None = None,
    ) -> str:
        source_kind = str(getattr(record, "source_kind", "")).strip().lower()
        source_ref = str(getattr(record, "source_ref", "")).strip()
        status = str(getattr(record, "status", "active")).strip().lower() or "active"
        mismatch = _credential_compatibility_error(
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
            return self._resolve_oauth_account_token(source_ref)
        if source_kind == "app_credential":
            if not source_ref:
                raise CredentialResolutionError(
                    f"credential binding '{binding_id.strip()}' has no app credential reference.",
                )
            return source_ref
        binding_value = self._configured_credential_source_from_record(record)
        if binding_value is None:
            raise CredentialResolutionError(
                f"credential binding '{binding_id.strip()}' has no source.",
            )
        return self.credential_resolver.resolve(
            binding_value,
            workspace_dir=workspace_dir,
            allow_literal=allow_literal,
        )

    def _configured_credential_source_from_record(self, record: object) -> str | None:
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

    def _resolve_oauth_account_token(self, account_id: str) -> str:
        if self.oauth_account_repository is None or self.oauth_token_store is None:
            raise CredentialResolutionError("OAuth account resolver is not configured.")
        try:
            from crxzipple.modules.access.application.oauth import AccessOAuthService

            return AccessOAuthService(
                repository=self.oauth_account_repository,
                token_store=self.oauth_token_store,
            ).resolve_access_token(account_id)
        except CredentialResolutionError:
            raise
        except Exception as exc:
            raise CredentialResolutionError(str(exc)) from exc

    def _configured_oauth_provider(self, provider_id: str | None) -> object | None:
        if not provider_id or self.oauth_account_repository is None:
            return None
        get_provider = getattr(self.oauth_account_repository, "get_oauth_provider", None)
        if not callable(get_provider):
            return None
        provider = get_provider(provider_id.strip())
        if provider is None or getattr(provider, "status", "active") != "active":
            return None
        return provider

    def _configured_credential_record(self, binding_id: str) -> object | None:
        view = self.config_view
        if view is None:
            return None
        get_binding = getattr(view, "get_credential_binding", None)
        if not callable(get_binding):
            return None
        return get_binding(binding_id.strip())


def parse_access_requirement(requirement: str) -> AccessRequirement:
    normalized = requirement.strip()
    if not normalized:
        return AccessRequirement(raw="")

    provider_kind, scopes = _split_scopes(normalized)
    provider: str | None = None
    kind: str | None = None
    if ":" in provider_kind:
        provider_value, kind_value = provider_kind.split(":", 1)
        provider = provider_value.strip() or None
        kind = kind_value.strip() or None
    else:
        kind = provider_kind.strip() or None
    return AccessRequirement(
        raw=normalized,
        provider=provider,
        kind=kind,
        scopes=scopes,
    )


def _split_scopes(value: str) -> tuple[str, tuple[str, ...]]:
    if not value.endswith(")") or "(" not in value:
        return value, ()
    head, raw_scopes = value[:-1].split("(", 1)
    scopes = tuple(
        scope.strip()
        for scope in raw_scopes.split(",")
        if scope is not None and scope.strip()
    )
    return head.strip(), scopes


def is_credential_binding(value: str) -> bool:
    normalized = value.strip()
    return normalized.startswith(("env:", "file:"))


def credential_binding_env_name(binding: str) -> str | None:
    normalized = binding.strip()
    if not normalized.startswith("env:"):
        return None
    env_name = normalized.removeprefix("env:").strip()
    return env_name or None


def canonical_credential_binding(binding: str) -> str:
    normalized = binding.strip()
    if normalized.startswith("env:"):
        return f"env:{normalized.removeprefix('env:').strip()}"
    if normalized.startswith("file:"):
        return f"file:{normalized.removeprefix('file:').strip()}"
    return normalized


def _single_scope_binding(requirement: AccessRequirement) -> str | None:
    if len(requirement.scopes) != 1:
        return None
    candidate = requirement.scopes[0].strip()
    if is_credential_binding(candidate):
        return candidate
    return None


def _display_credential_file_path(
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


def _safe_source_ref(source_kind: object, source_ref: object) -> str | None:
    normalized_kind = str(source_kind or "").strip().lower()
    normalized_ref = str(source_ref or "").strip()
    if not normalized_ref:
        return None
    if normalized_kind == "oauth_account":
        return normalized_ref
    if normalized_kind in {"env", "file"}:
        return f"{normalized_kind}:***"
    return "***"


def _oauth_provider_id_from_account_ref(account_ref: str) -> str:
    normalized = account_ref.strip()
    if ":" in normalized:
        return normalized.split(":", 1)[0].strip()
    return normalized


def _source_metadata(source_kind: object, source_ref: object) -> dict[str, object]:
    normalized_kind = str(source_kind or "").strip().lower()
    normalized_ref = str(source_ref or "").strip()
    metadata: dict[str, object] = {
        "source_kind": normalized_kind or None,
        "configured": bool(normalized_ref),
        "source_ref_redacted": bool(normalized_ref),
    }
    if normalized_kind == "env" and normalized_ref:
        metadata["reference_kind"] = "environment_variable"
    elif normalized_kind == "file" and normalized_ref:
        metadata["reference_kind"] = "file_path"
    elif normalized_kind == "oauth_account" and normalized_ref:
        metadata["source_ref_redacted"] = False
    return metadata


def _safe_masked_preview(source_kind: object, masked_preview: object) -> str | None:
    normalized_preview = str(masked_preview or "").strip()
    if not normalized_preview:
        return None
    normalized_kind = str(source_kind or "").strip().lower()
    if normalized_kind in {"env", "file"}:
        return f"{normalized_kind}:***"
    if normalized_kind in {"literal", "inline", "inline_credential", "secret"}:
        return "***"
    return normalized_preview


def _credential_record_audit_context(
    record: object,
    *,
    binding_id: str,
    consumer: AccessConsumerRef | None,
    trace_context: Mapping[str, object] | None,
) -> dict[str, Any]:
    source_kind = getattr(record, "source_kind", None)
    source_ref = getattr(record, "source_ref", None)
    context: dict[str, Any] = {
        "credential_binding_id": binding_id.strip(),
        "binding_kind": getattr(record, "binding_kind", None),
        "source_kind": source_kind,
        "asset_id": getattr(record, "asset_id", None),
        "status": getattr(record, "status", None),
        "masked_preview": _safe_masked_preview(
            source_kind,
            getattr(record, "masked_preview", None),
        ),
        "source_ref": _safe_source_ref(source_kind, source_ref),
        "source_metadata": _source_metadata(source_kind, source_ref),
    }
    if consumer is not None:
        context["consumer"] = _consumer_audit_context(consumer)
    safe_trace = _safe_trace_context(trace_context)
    if safe_trace:
        context["trace_context"] = safe_trace
    return context


def _direct_credential_audit_context(
    binding_value: str,
    *,
    consumer: AccessConsumerRef | None,
    trace_context: Mapping[str, object] | None,
    allow_literal: bool,
) -> dict[str, Any]:
    source_kind, source_ref = _source_kind_and_ref(
        binding_value,
        allow_literal=allow_literal,
    )
    context: dict[str, Any] = {
        "credential_binding_id": None,
        "source_kind": source_kind,
        "source_ref": _safe_source_ref(source_kind, source_ref),
        "source_metadata": _source_metadata(source_kind, source_ref),
    }
    if consumer is not None:
        context["consumer"] = _consumer_audit_context(consumer)
    safe_trace = _safe_trace_context(trace_context)
    if safe_trace:
        context["trace_context"] = safe_trace
    return context


def _source_kind_and_ref(
    binding_value: str,
    *,
    allow_literal: bool,
) -> tuple[str, str]:
    normalized = binding_value.strip()
    if normalized.startswith("env:"):
        return "env", normalized.removeprefix("env:")
    if normalized.startswith("file:"):
        return "file", normalized.removeprefix("file:")
    if normalized.startswith("oauth_account:"):
        return "oauth_account", normalized.removeprefix("oauth_account:")
    if normalized.startswith("app_credential:"):
        return "app_credential", normalized.removeprefix("app_credential:")
    if allow_literal:
        return "literal", normalized
    return "binding", normalized


def _consumer_audit_context(consumer: AccessConsumerRef) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "consumer_id": consumer.consumer_id,
        "module": consumer.module,
    }
    if consumer.component:
        payload["component"] = consumer.component
    if consumer.runtime_ref:
        payload["runtime_ref"] = consumer.runtime_ref
    if consumer.metadata:
        payload["metadata"] = _safe_audit_value(consumer.metadata)
    return payload


def _event_binding_id(binding_value: object) -> str:
    return str(binding_value or "").strip()


def _credential_resolution_event_payload(
    *,
    binding_id: str,
    expected_kind: str | None,
    consumer: AccessConsumerRef | None,
    allow_literal: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "binding_id": binding_id,
        "credential_binding_id": binding_id,
        "expected_kind": expected_kind,
        "allow_literal": allow_literal,
    }
    if consumer is not None:
        payload["consumer"] = _consumer_audit_context(consumer)
        payload["consumer_module"] = consumer.module
        payload["consumer_id"] = consumer.consumer_id
    return payload


def _safe_trace_context(
    trace_context: Mapping[str, object] | None,
) -> dict[str, Any]:
    if not trace_context:
        return {}
    return {
        str(key): _safe_audit_value(value, key=str(key))
        for key, value in trace_context.items()
    }


def _safe_audit_value(value: object, *, key: str | None = None) -> Any:
    if key is not None and _is_sensitive_audit_key(key):
        return "***"
    if isinstance(value, Mapping):
        return {
            str(nested_key): _safe_audit_value(nested_value, key=str(nested_key))
            for nested_key, nested_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [_safe_audit_value(item) for item in value]
    if isinstance(value, str):
        return _truncate_audit_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    return _truncate_audit_text(str(value))


def _is_sensitive_audit_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return any(
        marker in normalized
        for marker in (
            "api_key",
            "apikey",
            "authorization",
            "client_secret",
            "password",
            "raw",
            "secret",
            "token",
        )
    )


def _truncate_audit_text(value: str, *, limit: int = 240) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"


def _expected_kind_for_requirement(
    requirement: AccessRequirement,
    *,
    explicit: str | None,
) -> str | None:
    normalized_explicit = _normalize_binding_kind(explicit)
    if normalized_explicit is not None:
        return normalized_explicit
    kind = _normalize_binding_kind(requirement.kind)
    if kind is not None:
        return kind
    return None


def _expected_kind_from_binding_ref(
    binding: str | CredentialBindingRef,
    *,
    explicit: str | None,
) -> str | None:
    normalized_explicit = _normalize_binding_kind(explicit)
    if normalized_explicit is not None:
        return normalized_explicit
    if not isinstance(binding, CredentialBindingRef):
        return None
    normalized_ref_kind = _normalize_binding_kind(getattr(binding, "expected_kind", None))
    if normalized_ref_kind is not None:
        return normalized_ref_kind
    for key in ("expected_kind", "credential_kind", "binding_kind", "kind"):
        value = binding.metadata.get(key)
        normalized = _normalize_binding_kind(value if isinstance(value, str) else None)
        if normalized is not None:
            return normalized
    return _normalize_binding_kind(binding.source_type)


def _credential_compatibility_error(
    record: object,
    *,
    expected_kind: str | None,
    binding_id: str,
) -> str | None:
    binding_kind = _normalize_binding_kind(getattr(record, "binding_kind", None))
    source_kind = str(getattr(record, "source_kind", "") or "").strip().lower()
    normalized_id = binding_id.strip()
    if expected_kind is not None and binding_kind != expected_kind:
        return (
            "credential_kind_mismatch: credential binding "
            f"'{normalized_id}' is '{binding_kind or 'unknown'}' but requirement "
            f"expects '{expected_kind}'."
        )
    if source_kind == "oauth_account" and binding_kind not in _OAUTH_BINDING_KINDS:
        return (
            "credential_source_kind_mismatch: credential binding "
            f"'{normalized_id}' uses oauth_account source with "
            f"'{binding_kind or 'unknown'}' binding kind."
        )
    if binding_kind in _OAUTH_BINDING_KINDS and source_kind != "oauth_account":
        return (
            "credential_source_kind_mismatch: credential binding "
            f"'{normalized_id}' is '{binding_kind}' but source kind is "
            f"'{source_kind or 'unknown'}'."
        )
    return None


def _normalize_binding_kind(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    aliases = {
        "bearer": "bearer_token",
        "oauth": "oauth2_account",
        "oauth2": "oauth2_account",
        "openid": "openid_connect",
        "oidc": "openid_connect",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in _KNOWN_BINDING_KINDS else None


def _mismatch_readiness_status(message: str) -> AccessReadinessStatus:
    if message.startswith("credential_kind_mismatch:"):
        return AccessReadinessStatus.CREDENTIAL_KIND_MISMATCH
    return AccessReadinessStatus.CREDENTIAL_SOURCE_KIND_MISMATCH
