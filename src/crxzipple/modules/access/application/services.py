from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Mapping

from crxzipple.modules.access.domain import (
    AccessReadinessStatus,
    AccessRequirement,
    AccessRequirementReadiness,
    AccessSetupFlow,
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
from crxzipple.modules.access.application.configured_credentials import (
    AccessCredentialConfigView,
    configured_credential_record,
    configured_credential_source,
    configured_oauth_provider,
    resolve_configured_credential_record,
)
from crxzipple.modules.access.application.credential_requirement_rules import (
    canonical_credential_binding,
    credential_binding_env_name,
    credential_compatibility_error as _credential_compatibility_error,
    expected_kind_for_requirement as _expected_kind_for_requirement,
    expected_kind_from_binding_ref as _expected_kind_from_binding_ref,
    is_credential_binding,
    mismatch_readiness_status as _mismatch_readiness_status,
    parse_access_requirement,
    single_scope_binding as _single_scope_binding,
)
from crxzipple.modules.access.application.credential_resolver import CredentialResolver
from crxzipple.modules.access.application.credential_resolution_audit import (
    credential_record_audit_context,
    credential_resolution_event_payload,
    direct_credential_audit_context,
    event_binding_id,
    safe_masked_preview,
    safe_source_ref,
    source_metadata,
)
from crxzipple.modules.access.application.credential_setup_flows import (
    app_credential_setup_flow,
    codex_oauth_setup_flow,
    environment_setup_flow,
    file_setup_flow,
    inactive_credential_binding_setup_flow,
    invalid_environment_credential_flow,
    missing_credential_source_setup_flow,
    oauth_account_not_configured_flow,
    oauth_provider_id_from_account_ref,
    oauth_provider_not_configured_flow,
    oauth_provider_setup_flow,
    unsupported_access_requirement_flow,
    unsupported_access_setup_flow,
    unsupported_credential_source_setup_flow,
)
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessResolvedCredential,
    CredentialBindingRef,
)

__all__ = (
    "AccessApplicationService",
    "AccessCredentialConfigView",
    "CredentialResolver",
    "canonical_credential_binding",
    "credential_binding_env_name",
    "is_credential_binding",
    "parse_access_requirement",
)


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
                setup_flow=unsupported_access_requirement_flow(),
            )
        if normalized in self._ready_auth_requirement_set():
            return AccessRequirementReadiness(
                requirement=parsed,
                status=AccessReadinessStatus.READY,
                reason="requirement is marked ready by the access registry",
            )
        configured_record = configured_credential_record(self.config_view, normalized)
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
            record = configured_credential_record(self.config_view, normalized)
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
                resolve_configured_credential_record(
                    normalized,
                    record,
                    credential_resolver=self.credential_resolver,
                    oauth_account_repository=self.oauth_account_repository,
                    oauth_token_store=self.oauth_token_store,
                    workspace_dir=workspace_dir,
                    allow_literal=allow_literal,
                    expected_kind=expected_binding_kind,
                )
            else:
                binding_value = (
                    configured_credential_source(self.config_view, binding) or binding
                )
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
        event_target_id = event_binding_id(binding_value)
        requested_payload = credential_resolution_event_payload(
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
            record = configured_credential_record(self.config_view, binding_value)
            if record is not None:
                credential = resolve_configured_credential_record(
                    binding_value,
                    record,
                    credential_resolver=self.credential_resolver,
                    oauth_account_repository=self.oauth_account_repository,
                    oauth_token_store=self.oauth_token_store,
                    workspace_dir=workspace_dir,
                    allow_literal=allow_literal,
                    expected_kind=expected_binding_kind,
                )
                audit_context = credential_record_audit_context(
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
                configured_binding = configured_credential_source(
                    self.config_view,
                    binding_value,
                )
                if configured_binding is not None:
                    binding_value = configured_binding
                credential = self.credential_resolver.resolve(
                    binding_value,
                    workspace_dir=workspace_dir,
                    allow_literal=allow_literal,
                )
                audit_context = direct_credential_audit_context(
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
        record = configured_credential_record(self.config_view, binding_id)
        if record is None:
            return None
        return {
            "binding_id": getattr(record, "binding_id", binding_id),
            "binding_kind": getattr(record, "binding_kind", None),
            "source_kind": getattr(record, "source_kind", None),
            "asset_id": getattr(record, "asset_id", None),
            "status": getattr(record, "status", None),
            "masked_preview": safe_masked_preview(
                getattr(record, "source_kind", None),
                getattr(record, "masked_preview", None),
            ),
            "source_ref": safe_source_ref(
                getattr(record, "source_kind", None),
                getattr(record, "source_ref", None),
            ),
            "source_metadata": source_metadata(
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
            return unsupported_access_setup_flow("The access requirement is empty.")

        configured_record = configured_credential_record(self.config_view, normalized)
        if configured_record is not None:
            return self._configured_credential_setup_flow(
                normalized,
                configured_record,
                workspace_dir=workspace_dir,
            )

        if normalized.startswith("env:"):
            env_name = normalized.removeprefix("env:").strip()
            if not env_name:
                return invalid_environment_credential_flow()
            return environment_setup_flow(env_name)

        if normalized.startswith("file:"):
            raw_path = normalized.removeprefix("file:").strip()
            return file_setup_flow(
                raw_path,
                workspace_dir=workspace_dir,
            )

        parsed = parse_access_requirement(normalized)
        if parsed.kind in {"oauth_connector", "oauth", "openid_connector"}:
            provider = configured_oauth_provider(
                self.oauth_account_repository,
                parsed.provider,
            )
            if provider is not None:
                return oauth_provider_setup_flow(parsed, provider)
            return oauth_provider_not_configured_flow(parsed)

        return unsupported_access_setup_flow(
            f"Access does not know how to set up '{normalized}' yet.",
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
            return inactive_credential_binding_setup_flow(binding_id, status)
        if not source_kind or not source_ref:
            return missing_credential_source_setup_flow(binding_id)
        if source_kind in {"env", "file"}:
            return self.begin_setup(
                f"{source_kind}:{source_ref}",
                workspace_dir=workspace_dir,
            )
        if source_kind == "app_credential":
            return app_credential_setup_flow(
                binding_id=binding_id,
                source_kind=source_kind,
                source_ref=source_ref,
            )
        if source_kind == "oauth_account":
            provider_id = oauth_provider_id_from_account_ref(source_ref)
            if (
                provider_id == "openai-codex"
                or binding_id.strip() == "codex-oauth-default"
            ):
                return codex_oauth_setup_flow(
                    binding_id=binding_id,
                    source_ref=source_ref,
                    provider_id=provider_id,
                )
            provider = configured_oauth_provider(
                self.oauth_account_repository,
                provider_id,
            )
            if provider is not None and getattr(provider, "authorization_url", None):
                return self.begin_setup(
                    f"{provider_id}:oauth",
                    workspace_dir=workspace_dir,
                )
            return oauth_account_not_configured_flow(
                binding_id=binding_id,
                source_ref=source_ref,
                provider_id=provider_id,
            )
        return unsupported_credential_source_setup_flow(
            binding_id=binding_id,
            source_kind=source_kind,
        )

    def _ready_auth_requirement_set(self) -> set[str]:
        env_values = os.environ.get("CRXZIPPLE_READY_AUTH_REQUIREMENTS", "")
        return {
            item.strip()
            for item in (*self.ready_auth_requirements, *env_values.split(","))
            if item is not None and item.strip()
        }
