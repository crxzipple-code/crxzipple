from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Mapping, Protocol

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
from crxzipple.shared.access import AccessConsumerRef, CredentialBindingRef

_CODEX_AUTH_JSON_BINDINGS = {
    "codex_auth_json",
    "codex-auth-json",
    "codex_cli",
    "codex-cli",
}
_CODEX_AUTH_JSON_PREFIXES = tuple(f"{name}:" for name in _CODEX_AUTH_JSON_BINDINGS)


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
        if is_codex_auth_json_binding(normalized):
            return self._resolve_codex_auth_json(normalized)
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

    def _resolve_codex_auth_json(self, binding: str) -> str:
        path = codex_auth_json_path_for_binding(binding)
        token = load_codex_auth_json_access_token(path)
        if token is None:
            raise CredentialResolutionError(
                f"could not resolve a Codex access token from '{path}'.",
            )
        return token


@dataclass(slots=True)
class AccessApplicationService:
    credential_resolver: CredentialResolver = field(default_factory=CredentialResolver)
    ready_auth_requirements: tuple[str, ...] = ()
    config_view: AccessCredentialConfigView | None = None

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
        configured_binding = self._configured_credential_source(normalized)
        if configured_binding is not None:
            return self.check_credential_binding(
                configured_binding,
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
    ) -> AccessRequirementReadiness:
        parsed = requirement or parse_access_requirement(binding)
        binding_value = self._configured_credential_source(binding) or binding
        try:
            self.credential_resolver.resolve(
                binding_value,
                workspace_dir=workspace_dir,
                allow_literal=allow_literal,
            )
        except CredentialResolutionError as exc:
            normalized = binding.strip()
            unsupported = (
                normalized
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
                setup_flow=self.begin_setup(binding_value, workspace_dir=workspace_dir),
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
    ) -> str:
        del consumer, trace_context
        binding_value = (
            binding.source_ref if isinstance(binding, CredentialBindingRef) else binding
        )
        configured_binding = self._configured_credential_source(binding_value)
        if configured_binding is not None:
            binding_value = configured_binding
        return self.credential_resolver.resolve(
            binding_value,
            workspace_dir=workspace_dir,
            allow_literal=allow_literal,
        )

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

        if is_codex_auth_json_binding(normalized):
            path = codex_auth_json_path_for_binding(normalized)
            return AccessSetupFlow(
                kind=AccessSetupFlowKind.COMMAND,
                title="Authorize Codex",
                description=(
                    f"Run Codex login so access can read an access token from '{path}'."
                ),
                action_label="Run login command",
                command=("codex", "login"),
                path=str(path),
                metadata={"credential_binding": normalized},
                actions=(
                    AccessSetupAction(
                        kind=AccessSetupActionKind.RUN_COMMAND,
                        label="Run Codex login",
                        description="Run this command in a trusted terminal.",
                        command=("codex", "login"),
                        path=str(path),
                        metadata={"credential_binding": normalized},
                    ),
                ),
            )

        parsed = parse_access_requirement(normalized)
        if parsed.kind in {"oauth_connector", "oauth", "openid_connector"}:
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

    def _ready_auth_requirement_set(self) -> set[str]:
        env_values = os.environ.get("CRXZIPPLE_READY_AUTH_REQUIREMENTS", "")
        return {
            item.strip()
            for item in (*self.ready_auth_requirements, *env_values.split(","))
            if item is not None and item.strip()
        }

    def _configured_credential_source(self, binding_id: str) -> str | None:
        view = self.config_view
        if view is None:
            return None
        get_binding = getattr(view, "get_credential_binding", None)
        if not callable(get_binding):
            return None
        record = get_binding(binding_id.strip())
        if record is None:
            return None
        source_kind = str(getattr(record, "source_kind", "")).strip()
        source_ref = str(getattr(record, "source_ref", "")).strip()
        if not source_kind or not source_ref:
            return None
        if source_kind in {"env", "file"}:
            return f"{source_kind}:{source_ref}"
        if source_kind == "codex_auth_json":
            return (
                "codex_auth_json"
                if source_ref == str(default_codex_auth_json_path())
                else f"codex_auth_json:{source_ref}"
            )
        return source_ref


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


def default_codex_auth_json_path() -> Path:
    codex_home = os.getenv("CODEX_HOME")
    if isinstance(codex_home, str) and codex_home.strip():
        return Path(codex_home).expanduser() / "auth.json"
    return Path("~/.codex/auth.json").expanduser()


def codex_auth_json_path_for_binding(binding: str) -> Path:
    normalized = binding.strip()
    if normalized in _CODEX_AUTH_JSON_BINDINGS:
        return default_codex_auth_json_path()
    if normalized.startswith(_CODEX_AUTH_JSON_PREFIXES):
        _, raw_path = normalized.split(":", 1)
        if not raw_path.strip():
            raise CredentialResolutionError(
                "Codex auth json credential binding has no path.",
            )
        return Path(raw_path.strip()).expanduser()
    raise CredentialResolutionError(
        f"unsupported Codex auth json credential binding '{normalized}'.",
    )


def load_codex_auth_json_access_token(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise CredentialResolutionError(f"invalid codex auth json at '{path}'.") from exc

    if not isinstance(payload, dict):
        return None
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        return None
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        return None
    return access_token.strip()


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


def is_codex_auth_json_binding(binding: str) -> bool:
    normalized = binding.strip()
    return normalized in _CODEX_AUTH_JSON_BINDINGS or normalized.startswith(
        _CODEX_AUTH_JSON_PREFIXES,
    )


def is_credential_binding(value: str) -> bool:
    normalized = value.strip()
    return (
        normalized.startswith(("env:", "file:"))
        or is_codex_auth_json_binding(normalized)
    )


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
    if is_codex_auth_json_binding(normalized):
        return _canonical_codex_auth_json_binding(normalized)
    return normalized


def _canonical_codex_auth_json_binding(binding: str) -> str:
    normalized = binding.strip()
    if normalized in _CODEX_AUTH_JSON_BINDINGS:
        return "codex_auth_json"
    for prefix in _CODEX_AUTH_JSON_PREFIXES:
        if normalized.startswith(prefix):
            path = normalized.removeprefix(prefix).strip()
            return f"codex_auth_json:{path}" if path else "codex_auth_json:"
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
