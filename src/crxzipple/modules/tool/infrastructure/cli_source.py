from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from threading import Thread
import time
from typing import Any

from crxzipple.core.logger import get_logger
from crxzipple.modules.process.application import ProcessApplicationService
from crxzipple.modules.process.domain import ProcessOutputWindow
from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCandidate,
    ToolFunctionCatalogRecord,
    ToolFunctionRuntimeKind,
    ToolFunctionStatus,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryResult,
)
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
    ToolResultEnvelope,
)
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionPolicy,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolMode,
    ToolParameter,
    ToolRunResult,
    ToolDefinitionOrigin,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.runtimes.registry import ToolRuntimeRegistry
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
    CredentialBindingRef,
)
from crxzipple.shared.content_blocks import describe_content_for_text_fallback
from crxzipple.shared.domain.events import Event
from crxzipple.shared.event_contracts import TOOL_CLI_EVENT_NAMES


logger = get_logger(__name__)
TOOL_CLI_OUTPUT_OBSERVED_EVENT = TOOL_CLI_EVENT_NAMES[0]
CLI_OUTPUT_POLL_INTERVAL_SECONDS = 0.1
CLI_OUTPUT_EVENT_CHUNK_BYTES = 4000
CLI_CREDENTIAL_INJECTION_KINDS = frozenset({"env", "file"})
PROMOTED_ARG_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_FORBIDDEN_DIRECT_CREDENTIAL_SOURCE_PREFIXES = (
    "env:",
    "file:",
    "codex_auth_json",
    "codex-cli",
    "auth_ref",
)


GUIDED_CLI_ACTIONS: tuple[str, ...] = (
    "cli_help",
    "cli_execute",
    "cli_read_output",
    "cli_cancel",
)


@dataclass(frozen=True, slots=True)
class CliToolSourceConfig:
    source_id: str
    provider_name: str
    executable: str
    base_args: tuple[str, ...] = ()
    allowed_subcommands: tuple[str, ...] = ()
    denied_flags: tuple[str, ...] = ()
    mutating_subcommands: tuple[str, ...] = ()
    help_args: tuple[str, ...] = ("--help",)
    working_directory: Path = Path.cwd()
    allowed_roots: tuple[Path, ...] = ()
    timeout_seconds: int = 30
    output_limit_bytes: int = 16000
    shell: str = "/bin/zsh"
    max_concurrency: int | None = None
    credential_bindings: tuple["CliCredentialBindingConfig", ...] = ()
    promoted_functions: tuple["CliPromotedFunctionConfig", ...] = ()

    @classmethod
    def from_source(cls, source: ToolSourceCatalogRecord) -> "CliToolSourceConfig":
        provider = source.config.get("provider")
        if not isinstance(provider, Mapping):
            raise ToolValidationError(
                f"Configured CLI source '{source.source_id}' config.provider must be an object.",
            )

        command = _text_tuple(provider.get("command"))
        executable = _optional_text(provider.get("executable"))
        base_args = _text_tuple(provider.get("base_args"))
        if executable is None and command:
            executable = command[0]
            base_args = command[1:]
        if executable is None:
            raise ToolValidationError(
                f"Configured CLI source '{source.source_id}' requires config.provider.executable or command.",
            )

        provider_name = _required_text(
            provider.get("name"),
            field_name=f"{source.source_id}.provider.name",
        )
        working_directory = _resolve_directory(
            provider.get("working_directory"),
            default=Path.cwd(),
            field_name=f"{source.source_id}.provider.working_directory",
        )
        allowed_roots = tuple(
            _resolve_directory(
                root,
                default=working_directory,
                field_name=f"{source.source_id}.provider.allowed_roots",
            )
            for root in _text_tuple(provider.get("allowed_roots"))
        ) or (working_directory,)
        _ensure_path_in_roots(
            working_directory,
            allowed_roots=allowed_roots,
            field_name="working_directory",
        )

        config = cls(
            source_id=source.source_id,
            provider_name=provider_name,
            executable=_resolve_executable(executable),
            base_args=base_args,
            allowed_subcommands=_text_tuple(provider.get("allowed_subcommands")),
            denied_flags=_text_tuple(provider.get("denied_flags")),
            mutating_subcommands=_text_tuple(provider.get("mutating_subcommands")),
            help_args=(
                _text_tuple(provider.get("help_args"))
                or ("--help",)
            ),
            working_directory=working_directory,
            allowed_roots=allowed_roots,
            timeout_seconds=_positive_int(
                provider.get("timeout_seconds"),
                default=30,
            ),
            output_limit_bytes=_positive_int(
                provider.get("output_limit_bytes"),
                default=16000,
            ),
            shell=_optional_text(provider.get("shell")) or "/bin/zsh",
            max_concurrency=_optional_positive_int(provider.get("max_concurrency")),
            credential_bindings=_credential_binding_configs(
                provider.get("credential_bindings"),
                source_id=source.source_id,
            ),
            promoted_functions=_promoted_function_configs(
                provider.get("promoted_functions"),
                source_id=source.source_id,
            ),
        )
        config.validate_executable()
        if not config.allowed_subcommands:
            raise ToolValidationError(
                f"Configured CLI source '{source.source_id}' requires at least one allowed subcommand.",
            )
        for promoted in config.promoted_functions:
            config.validate_promoted_function(promoted)
        return config

    @property
    def source_marker(self) -> str:
        return f"cli:{self.source_id}"

    def validate_executable(self) -> None:
        executable_path = Path(self.executable)
        if executable_path.is_absolute():
            if not executable_path.exists() or not os.access(executable_path, os.X_OK):
                raise ToolValidationError(
                    f"CLI executable '{self.executable}' does not exist or is not executable.",
                )
            return
        if shutil.which(self.executable) is None:
            raise ToolValidationError(
                f"CLI executable '{self.executable}' was not found on PATH.",
            )

    def build_help_argv(self, *, subcommand: str | None = None) -> tuple[str, ...]:
        argv = [self.executable, *self.base_args]
        if subcommand:
            self.validate_subcommand(subcommand)
            argv.append(subcommand)
        argv.extend(self.help_args)
        self.validate_args(argv[1:])
        return tuple(argv)

    def build_execute_argv(
        self,
        *,
        subcommand: str,
        args: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        self.validate_subcommand(subcommand)
        argv = (self.executable, *self.base_args, subcommand, *args)
        self.validate_args(argv[1:])
        return argv

    def build_promoted_argv(
        self,
        promoted: "CliPromotedFunctionConfig",
        *,
        arguments: Mapping[str, Any],
    ) -> tuple[str, ...]:
        args = promoted.render_args(arguments)
        return self.build_execute_argv(
            subcommand=promoted.subcommand,
            args=args,
        )

    def promoted_function(self, function_id: str) -> "CliPromotedFunctionConfig | None":
        normalized = function_id.strip()
        for promoted in self.promoted_functions:
            if promoted.function_id == normalized:
                return promoted
        return None

    def validate_promoted_function(
        self,
        promoted: "CliPromotedFunctionConfig",
    ) -> None:
        self.validate_subcommand(promoted.subcommand)
        literal_args = tuple(
            arg
            for arg in promoted.args
            if "{" not in arg and "}" not in arg
        )
        self.validate_args((promoted.subcommand, *literal_args))

    def validate_subcommand(self, subcommand: str) -> None:
        normalized = subcommand.strip()
        if not normalized:
            raise ToolValidationError("CLI subcommand is required.")
        if self.allowed_subcommands and normalized not in self.allowed_subcommands:
            allowed = ", ".join(self.allowed_subcommands)
            raise ToolValidationError(
                f"CLI subcommand '{normalized}' is not allowed. Allowed: {allowed}.",
            )

    def validate_args(self, args: tuple[str, ...]) -> None:
        for arg in args:
            value = arg.strip()
            if not value:
                raise ToolValidationError("CLI argv entries cannot be empty.")
            self._validate_denied_flag(value)
            self._validate_path_arg(value)

    def _validate_denied_flag(self, value: str) -> None:
        for denied in self.denied_flags:
            if value == denied or value.startswith(f"{denied}="):
                raise ToolValidationError(f"CLI flag '{denied}' is denied by policy.")

    def _validate_path_arg(self, value: str) -> None:
        candidates: list[str] = []
        if "=" in value and value.startswith("-"):
            _, raw_value = value.split("=", 1)
            candidates.append(raw_value)
        elif "/" in value or value.startswith("."):
            candidates.append(value)
        for candidate in candidates:
            if not candidate or "://" in candidate:
                continue
            path = Path(candidate)
            if not path.is_absolute():
                path = self.working_directory / path
            _ensure_path_in_roots(
                path.resolve(),
                allowed_roots=self.allowed_roots,
                field_name="argv path",
            )


@dataclass(frozen=True, slots=True)
class CliCredentialBindingConfig:
    binding_id: str
    injection: str = "env"
    env_name: str | None = None
    file_env_name: str | None = None
    file_name: str = "credential"
    expected_kind: AccessCredentialKind = AccessCredentialKind.API_KEY
    provider: str | None = None
    slot: str | None = None
    display_name: str | None = None


@dataclass(frozen=True, slots=True)
class CliPromotedFunctionParameterConfig:
    name: str
    data_type: str = "string"
    description: str = ""
    required: bool = True

    def as_tool_parameter(self) -> ToolParameter:
        return ToolParameter(
            name=self.name,
            data_type=self.data_type,
            description=self.description,
            required=self.required,
        )


@dataclass(frozen=True, slots=True)
class CliPromotedFunctionConfig:
    function_id: str
    name: str
    description: str
    subcommand: str
    args: tuple[str, ...] = ()
    parameters: tuple[CliPromotedFunctionParameterConfig, ...] = ()
    initial_output_limit: int | None = None
    mutates_state: bool = False
    required_effect_ids: tuple[str, ...] = ()

    def render_args(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        rendered: list[str] = []
        for template in self.args:
            exact_match = PROMOTED_ARG_PATTERN.fullmatch(template)
            if exact_match is not None:
                name = exact_match.group(1)
                value = _promoted_argument_value(
                    arguments,
                    name,
                    parameters=self.parameters,
                    embedded=False,
                )
                if value is None:
                    continue
                if isinstance(value, list | tuple):
                    rendered.extend(_promoted_scalar_text(item, name) for item in value)
                    continue
                rendered.append(_promoted_scalar_text(value, name))
                continue

            names = PROMOTED_ARG_PATTERN.findall(template)
            if not names:
                rendered.append(template)
                continue
            value_by_name = {
                name: _promoted_argument_value(
                    arguments,
                    name,
                    parameters=self.parameters,
                    embedded=True,
                )
                for name in names
            }

            def replace(match: re.Match[str]) -> str:
                name = match.group(1)
                value = value_by_name[name]
                if isinstance(value, list | tuple):
                    raise ToolValidationError(
                        f"CLI promoted argument '{name}' cannot expand an array inside argv template.",
                    )
                return _promoted_scalar_text(value, name)

            rendered.append(PROMOTED_ARG_PATTERN.sub(replace, template))
        return tuple(rendered)

    def metadata_payload(self) -> dict[str, Any]:
        return {
            "id": self.function_id,
            "name": self.name,
            "description": self.description,
            "subcommand": self.subcommand,
            "args": self.args,
            "parameters": tuple(
                {
                    "name": parameter.name,
                    "data_type": parameter.data_type,
                    "description": parameter.description,
                    "required": parameter.required,
                }
                for parameter in self.parameters
            ),
            "initial_output_limit": self.initial_output_limit,
            "mutates_state": self.mutates_state,
            "required_effect_ids": self.required_effect_ids,
        }


@dataclass(frozen=True, slots=True)
class _CliCredentialInjection:
    env: dict[str, str]
    cleanup_paths: tuple[Path, ...]
    metadata: tuple[dict[str, str | None], ...]
    redactions: tuple[str, ...] = ()

    def cleanup(self) -> None:
        for path in self.cleanup_paths:
            try:
                if path.is_file():
                    path.unlink(missing_ok=True)
                parent = path.parent
                if parent.name.startswith("crxzipple-tool-credential-"):
                    parent.rmdir()
            except OSError:
                logger.debug(
                    "failed to cleanup CLI credential temp path",
                    extra={"path": str(path)},
                )


def discover_cli_source(
    source: ToolSourceCatalogRecord,
) -> ToolSourceDiscoveryResult:
    config = CliToolSourceConfig.from_source(source)
    promoted_candidates = tuple(
        _promoted_cli_candidate(source, config, promoted)
        for promoted in config.promoted_functions
    )
    return ToolSourceDiscoveryResult.completed(
        source_id=source.source_id,
        candidates=(
            *(
                _guided_cli_candidate(source, config, action)
                for action in GUIDED_CLI_ACTIONS
            ),
            *promoted_candidates,
        ),
        metadata={
            "source": "configured_tool_provider",
            "package_kind": "cli",
            "provider_name": config.provider_name,
            "actions": GUIDED_CLI_ACTIONS,
            "promoted_functions": tuple(
                promoted.function_id for promoted in config.promoted_functions
            ),
        },
    )


def register_cli_guided_handlers(
    registry: ToolRuntimeRegistry,
    *,
    source: ToolSourceCatalogRecord,
    functions: tuple[ToolFunctionCatalogRecord, ...],
    process_service: ProcessApplicationService,
    credential_provider: Any | None = None,
    events_service: Any | None = None,
    max_concurrency: int | None = None,
    replace: bool = False,
) -> None:
    config = CliToolSourceConfig.from_source(source)
    runtime = CliGuidedRuntime(
        config,
        process_service=process_service,
        credential_provider=credential_provider,
        events_service=events_service,
    )
    for function in functions:
        if function.status is not ToolFunctionStatus.ACTIVE or not function.enabled:
            continue
        action = str(function.metadata.get("cli_action") or "").strip()
        handler = runtime.handler_for(action, metadata=function.metadata)
        if handler is None:
            continue
        registry.register(
            function.handler_ref,
            handler,
            concurrency_key=f"cli:{config.provider_name}",
            max_concurrency=config.max_concurrency or max_concurrency,
            replace=replace,
        )


class CliGuidedRuntime:
    def __init__(
        self,
        config: CliToolSourceConfig,
        *,
        process_service: ProcessApplicationService,
        credential_provider: Any | None = None,
        events_service: Any | None = None,
    ) -> None:
        self.config = config
        self.process_service = process_service
        self.credential_provider = credential_provider
        self.events_service = events_service

    def handler_for(self, action: str, *, metadata: Mapping[str, Any] | None = None):
        if action == "cli_promoted_execute":
            promoted_id = _optional_text(
                (metadata or {}).get("promoted_function_id"),
            )
            if promoted_id is None:
                return None
            promoted = self.config.promoted_function(promoted_id)
            if promoted is None:
                return None
            return self.promoted_handler_for(promoted)
        return {
            "cli_help": self.cli_help,
            "cli_execute": self.cli_execute,
            "cli_read_output": self.cli_read_output,
            "cli_cancel": self.cli_cancel,
        }.get(action)

    def promoted_handler_for(self, promoted: CliPromotedFunctionConfig):
        async def handler(arguments: dict[str, Any]) -> ToolRunResult:
            return await self.cli_promoted_execute(promoted, arguments)

        return handler

    async def cli_help(self, arguments: dict[str, Any]) -> ToolRunResult:
        subcommand = _optional_text(arguments.get("subcommand"))
        argv = self.config.build_help_argv(subcommand=subcommand)
        injection = self._resolve_credential_injection("cli_help")
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                list(argv),
                cwd=str(self.config.working_directory),
                text=True,
                capture_output=True,
                timeout=self.config.timeout_seconds,
                check=False,
                env=_process_env(injection.env),
            )
            details = {
                "argv": _sanitized_argv(argv),
                "exit_code": completed.returncode,
                "stdout": _truncate(completed.stdout, self.config.output_limit_bytes),
                "stderr": _truncate(completed.stderr, self.config.output_limit_bytes),
                "working_directory": str(self.config.working_directory),
                "credential_injections": injection.metadata,
                "runtime_facts": _cli_runtime_facts(
                    self.config,
                    action="cli_help",
                    argv=argv,
                ),
            }
            return ToolRunResult.text(
                _render_cli_output(details),
                details=details,
                metadata={
                    "source_id": self.config.source_id,
                    "provider": self.config.provider_name,
                    "cli_action": "cli_help",
                    TOOL_RESULT_ENVELOPE_METADATA_KEY: _cli_help_result_envelope(
                        details,
                        source_id=self.config.source_id,
                        provider_name=self.config.provider_name,
                    ).to_payload(),
                },
            )
        finally:
            injection.cleanup()

    async def cli_execute(self, arguments: dict[str, Any]) -> ToolRunResult:
        subcommand = _required_text(
            arguments.get("subcommand"),
            field_name="subcommand",
        )
        args = _text_tuple(arguments.get("args"))
        argv = self.config.build_execute_argv(subcommand=subcommand, args=args)
        return await self._start_process(
            argv=argv,
            arguments=arguments,
            action="cli_execute",
            initial_output_limit=_positive_int(
                arguments.get("initial_output_limit"),
                default=min(self.config.output_limit_bytes, 4000),
            ),
            process_metadata={},
        )

    async def cli_promoted_execute(
        self,
        promoted: CliPromotedFunctionConfig,
        arguments: dict[str, Any],
    ) -> ToolRunResult:
        argv = self.config.build_promoted_argv(promoted, arguments=arguments)
        initial_output_limit = _positive_int(
            arguments.get("initial_output_limit"),
            default=(
                promoted.initial_output_limit
                or min(self.config.output_limit_bytes, 4000)
            ),
        )
        return await self._start_process(
            argv=argv,
            arguments=arguments,
            action="cli_promoted_execute",
            initial_output_limit=initial_output_limit,
            process_metadata={
                "promoted_function_id": promoted.function_id,
                "promoted_function_name": promoted.name,
            },
        )

    async def _start_process(
        self,
        *,
        argv: tuple[str, ...],
        arguments: Mapping[str, Any],
        action: str,
        initial_output_limit: int,
        process_metadata: Mapping[str, Any],
    ) -> ToolRunResult:
        command = shlex.join(argv)
        injection = self._resolve_credential_injection(action)
        try:
            session = await asyncio.to_thread(
                self.process_service.start_command,
                command=command,
                shell=self.config.shell,
                working_directory=str(self.config.working_directory),
                session_key=_optional_text(arguments.get("session_key")),
                env=injection.env,
                metadata={
                    "owner": "tool.cli_source",
                    "source_id": self.config.source_id,
                    "provider": self.config.provider_name,
                    "cli_action": action,
                    "argv": _sanitized_argv(argv),
                    "credential_injections": injection.metadata,
                    **dict(process_metadata),
                },
            )
        except Exception:
            injection.cleanup()
            raise
        self._observe_process_output(
            process_id=session.id,
            session_key=session.session_key,
            cleanup_paths=injection.cleanup_paths,
            redactions=injection.redactions,
        )
        initial_limit = _positive_int(
            arguments.get("initial_output_limit"),
            default=min(self.config.output_limit_bytes, 4000),
        )
        output = await asyncio.to_thread(
            self.process_service.read_output,
            process_id=session.id,
            limit=min(initial_limit, self.config.output_limit_bytes),
        )
        details = _process_output_payload(output) | {
            "argv": _sanitized_argv(argv),
            "working_directory": str(self.config.working_directory),
            "credential_injections": injection.metadata,
            "runtime_facts": _cli_runtime_facts(
                self.config,
                action=action,
                argv=argv,
            ),
            "continuation": _process_continuation_payload(
                output,
                default_limit=self.config.output_limit_bytes,
            ),
            **dict(process_metadata),
        }
        envelope = _cli_process_result_envelope(
            details,
            source_id=self.config.source_id,
            provider_name=self.config.provider_name,
            action=action,
            output=output,
        )
        return ToolRunResult.text(
            describe_content_for_text_fallback(details),
            details=details,
            metadata={
                "source_id": self.config.source_id,
                "provider": self.config.provider_name,
                "cli_action": action,
                "process_id": session.id,
                TOOL_RESULT_ENVELOPE_METADATA_KEY: envelope.to_payload(),
                **dict(process_metadata),
            },
        )

    def _observe_process_output(
        self,
        *,
        process_id: str,
        session_key: str | None,
        cleanup_paths: tuple[Path, ...] = (),
        redactions: tuple[str, ...] = (),
    ) -> None:
        if self.events_service is None and not cleanup_paths:
            return
        observer = _CliProcessOutputObserver(
            config=self.config,
            process_service=self.process_service,
            events_service=self.events_service,
            process_id=process_id,
            session_key=session_key,
            cleanup_paths=cleanup_paths,
            redactions=redactions,
        )
        observer.start()

    def _resolve_credential_injection(self, action: str) -> _CliCredentialInjection:
        if action not in {"cli_execute", "cli_promoted_execute"} or not self.config.credential_bindings:
            return _CliCredentialInjection(env={}, cleanup_paths=(), metadata=())
        if self.credential_provider is None:
            raise ToolValidationError(
                f"Configured CLI source '{self.config.source_id}' requires credential_provider.",
            )
        env: dict[str, str] = {}
        cleanup_paths: list[Path] = []
        metadata: list[dict[str, str | None]] = []
        redactions: list[str] = []
        try:
            for binding in self.config.credential_bindings:
                secret = self._resolve_credential(binding, action=action)
                if secret:
                    redactions.append(secret)
                if binding.injection == "env":
                    assert binding.env_name is not None
                    env[binding.env_name] = secret
                    metadata.append(_credential_injection_metadata(binding))
                    continue
                assert binding.file_env_name is not None
                credential_file = _write_credential_temp_file(
                    secret,
                    file_name=binding.file_name,
                )
                cleanup_paths.append(credential_file)
                env[binding.file_env_name] = str(credential_file)
                metadata.append(_credential_injection_metadata(binding))
        except Exception:
            _CliCredentialInjection(
                env=env,
                cleanup_paths=tuple(cleanup_paths),
                metadata=tuple(metadata),
                redactions=tuple(redactions),
            ).cleanup()
            raise
        return _CliCredentialInjection(
            env=env,
            cleanup_paths=tuple(cleanup_paths),
            metadata=tuple(metadata),
            redactions=tuple(redactions),
        )

    def _resolve_credential(
        self,
        binding: CliCredentialBindingConfig,
        *,
        action: str,
    ) -> str:
        try:
            return self.credential_provider.resolve_credential(
                CredentialBindingRef(
                    binding_id=binding.binding_id,
                    source_type="binding",
                    source_ref=binding.binding_id,
                    expected_kind=binding.expected_kind,
                    metadata={
                        "provider": binding.provider,
                        "slot": binding.slot or binding.binding_id,
                        "source_id": self.config.source_id,
                        "cli_action": action,
                    },
                ),
                consumer=AccessConsumerRef(
                    consumer_id=f"tool.cli_source:{self.config.source_id}:{action}",
                    module="tool",
                    component="cli_source",
                    runtime_ref=f"cli.{self.config.source_id}.{action}",
                    metadata={
                        "provider": self.config.provider_name,
                        "source_id": self.config.source_id,
                    },
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise ToolValidationError(
                f"Configured CLI source '{self.config.source_id}' could not resolve credential binding '{binding.binding_id}'.",
            ) from exc

    async def cli_read_output(self, arguments: dict[str, Any]) -> ToolRunResult:
        process_id = _required_text(arguments.get("process_id"), field_name="process_id")
        output = await asyncio.to_thread(
            self.process_service.read_output,
            process_id=process_id,
            stdout_offset=_non_negative_int(arguments.get("stdout_offset")),
            stderr_offset=_non_negative_int(arguments.get("stderr_offset")),
            limit=min(
                _positive_int(arguments.get("limit"), default=4000),
                self.config.output_limit_bytes,
            ),
        )
        details = _process_output_payload(output)
        details["runtime_facts"] = _cli_runtime_facts(
            self.config,
            action="cli_read_output",
            argv=(),
        )
        details["continuation"] = _process_continuation_payload(
            output,
            default_limit=self.config.output_limit_bytes,
        )
        envelope = _cli_process_result_envelope(
            details,
            source_id=self.config.source_id,
            provider_name=self.config.provider_name,
            action="cli_read_output",
            output=output,
        )
        return ToolRunResult.text(
            describe_content_for_text_fallback(details),
            details=details,
            metadata={
                "source_id": self.config.source_id,
                "provider": self.config.provider_name,
                "cli_action": "cli_read_output",
                "process_id": process_id,
                TOOL_RESULT_ENVELOPE_METADATA_KEY: envelope.to_payload(),
            },
        )

    async def cli_cancel(self, arguments: dict[str, Any]) -> ToolRunResult:
        process_id = _required_text(arguments.get("process_id"), field_name="process_id")
        session = await asyncio.to_thread(
            self.process_service.terminate_session,
            process_id=process_id,
        )
        details = {
            "process_id": session.id,
            "status": session.status.value,
            "exit_code": session.exit_code,
            "started_at": session.started_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        }
        return ToolRunResult.text(
            describe_content_for_text_fallback(details),
            details=details,
            metadata={
                "source_id": self.config.source_id,
                "provider": self.config.provider_name,
                "cli_action": "cli_cancel",
                "process_id": process_id,
            },
        )


@dataclass(slots=True)
class _CliProcessOutputObserver:
    config: CliToolSourceConfig
    process_service: ProcessApplicationService
    events_service: Any | None
    process_id: str
    session_key: str | None
    cleanup_paths: tuple[Path, ...] = ()
    redactions: tuple[str, ...] = ()
    poll_interval_seconds: float = CLI_OUTPUT_POLL_INTERVAL_SECONDS

    def start(self) -> None:
        thread = Thread(
            target=self._run,
            name=f"tool-cli-output-{self.process_id[:8]}",
            daemon=True,
        )
        thread.start()

    def _run(self) -> None:
        stdout_offset = 0
        stderr_offset = 0
        while True:
            try:
                output = self.process_service.read_output(
                    process_id=self.process_id,
                    stdout_offset=stdout_offset,
                    stderr_offset=stderr_offset,
                    limit=min(
                        self.config.output_limit_bytes,
                        CLI_OUTPUT_EVENT_CHUNK_BYTES,
                    ),
                )
            except Exception:
                logger.exception(
                    "failed to observe CLI process output",
                    extra={
                        "process_id": self.process_id,
                        "source_id": self.config.source_id,
                    },
                )
                self._cleanup()
                return

            self._publish_output(output, stream="stdout")
            self._publish_output(output, stream="stderr")
            stdout_offset = output.next_stdout_offset
            stderr_offset = output.next_stderr_offset
            if output.status.value != "running":
                self._publish_status(output)
                self._cleanup()
                return
            time.sleep(max(float(self.poll_interval_seconds), 0.02))

    def _publish_output(
        self,
        output: ProcessOutputWindow,
        *,
        stream: str,
    ) -> None:
        if stream == "stdout":
            text = output.stdout
            offset = output.stdout_offset
            next_offset = output.next_stdout_offset
        else:
            text = output.stderr
            offset = output.stderr_offset
            next_offset = output.next_stderr_offset
        if not text:
            return
        self._publish(
            stream=stream,
            text=text,
            offset=offset,
            next_offset=next_offset,
            output=output,
        )

    def _publish_status(self, output: ProcessOutputWindow) -> None:
        self._publish(
            stream="status",
            text="",
            offset=0,
            next_offset=0,
            output=output,
        )

    def _publish(
        self,
        *,
        stream: str,
        text: str,
        offset: int,
        next_offset: int,
        output: ProcessOutputWindow,
    ) -> None:
        if self.events_service is None:
            return
        event_text = _redact_cli_output(text, self.redactions)
        try:
            self.events_service.publish(
                Event(
                    name=TOOL_CLI_OUTPUT_OBSERVED_EVENT,
                    kind="live",
                    ordering_key=self.process_id,
                    payload={
                        "event_name": TOOL_CLI_OUTPUT_OBSERVED_EVENT,
                        "source_id": self.config.source_id,
                        "provider": self.config.provider_name,
                        "process_id": self.process_id,
                        "session_key": self.session_key,
                        "stream": stream,
                        "offset": offset,
                        "next_offset": next_offset,
                        "text": event_text,
                        "text_length": len(event_text),
                        "status": output.status.value,
                        "exit_code": output.exit_code,
                        "level": _cli_output_event_level(stream, output),
                        "summary": _cli_output_event_summary(
                            stream,
                            event_text,
                            output,
                        ),
                        "display_label": _cli_output_event_label(stream),
                        "display_summary": _cli_output_event_summary(
                            stream,
                            event_text,
                            output,
                        ),
                        "display_tone": _cli_output_event_tone(stream, output),
                        "entity_type": "tool_cli_process",
                        "entity_id": self.process_id,
                    },
                ),
            )
        except Exception:
            logger.exception(
                "failed to publish CLI process output event",
                extra={
                    "process_id": self.process_id,
                    "source_id": self.config.source_id,
                    "stream": stream,
                },
            )

    def _cleanup(self) -> None:
        _CliCredentialInjection(
            env={},
            cleanup_paths=self.cleanup_paths,
            metadata=(),
        ).cleanup()


def _guided_cli_candidate(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    action: str,
) -> ToolFunctionCandidate:
    spec = _guided_cli_spec(source, config, action)
    return ToolFunctionCandidate.from_tool_spec(
        spec,
        source_id=source.source_id,
        stable_key=f"cli.{source.source_id}.{action}",
        runtime_kind=ToolFunctionRuntimeKind.CLI,
        handler_ref=spec.runtime_key,
        metadata={
            "source": "configured_tool_provider",
            "package_kind": "cli",
            "provider_name": config.provider_name,
            "cli_action": action,
        },
    )


def _promoted_cli_candidate(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    promoted: CliPromotedFunctionConfig,
) -> ToolFunctionCandidate:
    spec = _promoted_cli_spec(source, config, promoted)
    return ToolFunctionCandidate.from_tool_spec(
        spec,
        source_id=source.source_id,
        stable_key=f"cli.{source.source_id}.promoted.{promoted.function_id}",
        runtime_kind=ToolFunctionRuntimeKind.CLI,
        handler_ref=spec.runtime_key,
        metadata={
            "source": "configured_tool_provider",
            "package_kind": "cli",
            "provider_name": config.provider_name,
            "cli_action": "cli_promoted_execute",
            "promoted_function_id": promoted.function_id,
            "promoted_function": promoted.metadata_payload(),
        },
    )


def _guided_cli_spec(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    action: str,
) -> ToolSpec:
    return ToolSpec(
        id=f"{_safe_tool_id(source.source_id)}_{action}",
        name=_guided_cli_name(config, action),
        description=_guided_cli_description(config, action),
        provider_name=config.provider_name,
        parameters=_guided_cli_parameters(action),
        tags=("cli", "guided", config.provider_name),
        required_effect_ids=_guided_cli_effects(config, action),
        runtime_requirement_sets=((config.source_marker,),),
        execution_policy=_guided_cli_policy(config, action),
        execution_support=ToolExecutionSupport(
            supported_modes=(ToolMode.INLINE,),
            supported_strategies=(ToolExecutionStrategy.ASYNC,),
            supported_environments=(ToolEnvironment.REMOTE,),
        ),
        definition_origin=ToolDefinitionOrigin.REMOTE_DISCOVERY,
        runtime_key=f"cli.{_safe_tool_id(source.source_id)}.{action}",
        credential_requirements=_guided_cli_credential_requirements(
            source,
            config,
            action,
        ),
    )


def _promoted_cli_spec(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    promoted: CliPromotedFunctionConfig,
) -> ToolSpec:
    safe_source_id = _safe_tool_id(source.source_id)
    safe_function_id = _safe_tool_id(promoted.function_id)
    return ToolSpec(
        id=f"{safe_source_id}_{safe_function_id}",
        name=promoted.name,
        description=promoted.description,
        provider_name=config.provider_name,
        parameters=tuple(
            parameter.as_tool_parameter()
            for parameter in promoted.parameters
        ),
        tags=("cli", "promoted", config.provider_name),
        required_effect_ids=_promoted_cli_effects(config, promoted),
        runtime_requirement_sets=((config.source_marker,),),
        execution_policy=_promoted_cli_policy(config, promoted),
        execution_support=ToolExecutionSupport(
            supported_modes=(ToolMode.INLINE,),
            supported_strategies=(ToolExecutionStrategy.ASYNC,),
            supported_environments=(ToolEnvironment.REMOTE,),
        ),
        definition_origin=ToolDefinitionOrigin.REMOTE_DISCOVERY,
        runtime_key=f"cli.{safe_source_id}.promoted.{safe_function_id}",
        credential_requirements=_promoted_cli_credential_requirements(
            source,
            config,
            promoted,
        ),
    )


def _guided_cli_name(config: CliToolSourceConfig, action: str) -> str:
    label = action.removeprefix("cli_").replace("_", " ").title()
    return f"{config.provider_name} {label}"


def _guided_cli_description(config: CliToolSourceConfig, action: str) -> str:
    if action == "cli_help":
        return f"Read help output from configured CLI source '{config.provider_name}'."
    if action == "cli_execute":
        return f"Start a governed command for configured CLI source '{config.provider_name}'."
    if action == "cli_read_output":
        return f"Read stdout/stderr from a governed CLI process for '{config.provider_name}'."
    if action == "cli_cancel":
        return f"Cancel a governed CLI process for '{config.provider_name}'."
    return f"Run guided CLI action '{action}' for '{config.provider_name}'."


def _guided_cli_parameters(action: str) -> tuple[ToolParameter, ...]:
    if action == "cli_help":
        return (
            ToolParameter(
                name="subcommand",
                data_type="string",
                description="Optional allowed subcommand to inspect.",
                required=False,
            ),
        )
    if action == "cli_execute":
        return (
            ToolParameter(
                name="subcommand",
                data_type="string",
                description="Allowed subcommand to execute.",
            ),
            ToolParameter(
                name="args",
                data_type="array[string]",
                description="Additional argv entries allowed by source policy.",
                required=False,
            ),
            ToolParameter(
                name="session_key",
                data_type="string",
                description="Optional caller correlation key for the process session.",
                required=False,
            ),
            ToolParameter(
                name="initial_output_limit",
                data_type="integer",
                description="Initial stdout/stderr bytes to read after spawning.",
                required=False,
            ),
        )
    if action == "cli_read_output":
        return (
            ToolParameter(name="process_id", data_type="string", description="Process session id."),
            ToolParameter(name="stdout_offset", data_type="integer", required=False),
            ToolParameter(name="stderr_offset", data_type="integer", required=False),
            ToolParameter(name="limit", data_type="integer", required=False),
        )
    if action == "cli_cancel":
        return (
            ToolParameter(name="process_id", data_type="string", description="Process session id."),
        )
    return ()


def _guided_cli_effects(
    config: CliToolSourceConfig,
    action: str,
) -> tuple[str, ...]:
    if action == "cli_execute" and config.mutating_subcommands:
        return ("tool.cli.mutate",)
    if action == "cli_cancel":
        return ("tool.cli.cancel",)
    return ()


def _guided_cli_policy(
    config: CliToolSourceConfig,
    action: str,
) -> ToolExecutionPolicy:
    mutates = action == "cli_execute" and bool(config.mutating_subcommands)
    return ToolExecutionPolicy(
        timeout_seconds=config.timeout_seconds,
        requires_confirmation=mutates or action == "cli_cancel",
        mutates_state=mutates or action == "cli_cancel",
    )


def _promoted_cli_effects(
    config: CliToolSourceConfig,
    promoted: CliPromotedFunctionConfig,
) -> tuple[str, ...]:
    if promoted.required_effect_ids:
        return promoted.required_effect_ids
    if promoted.mutates_state or promoted.subcommand in config.mutating_subcommands:
        return ("tool.cli.mutate",)
    return ()


def _promoted_cli_policy(
    config: CliToolSourceConfig,
    promoted: CliPromotedFunctionConfig,
) -> ToolExecutionPolicy:
    mutates = promoted.mutates_state or promoted.subcommand in config.mutating_subcommands
    return ToolExecutionPolicy(
        timeout_seconds=config.timeout_seconds,
        requires_confirmation=mutates,
        mutates_state=mutates,
    )


def _guided_cli_credential_requirements(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    action: str,
) -> tuple[AccessCredentialRequirementSet, ...]:
    if action != "cli_execute" or not config.credential_bindings:
        return ()
    return _cli_credential_requirements(
        source,
        config,
        action=action,
        runtime_ref=f"cli.{source.source_id}.{action}",
        requirement_set_id=f"{source.source_id}.{action}.credentials",
    )


def _promoted_cli_credential_requirements(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    promoted: CliPromotedFunctionConfig,
) -> tuple[AccessCredentialRequirementSet, ...]:
    if not config.credential_bindings:
        return ()
    return _cli_credential_requirements(
        source,
        config,
        action="cli_promoted_execute",
        runtime_ref=f"cli.{source.source_id}.promoted.{promoted.function_id}",
        requirement_set_id=(
            f"{source.source_id}.promoted.{promoted.function_id}.credentials"
        ),
    )


def _cli_credential_requirements(
    source: ToolSourceCatalogRecord,
    config: CliToolSourceConfig,
    *,
    action: str,
    runtime_ref: str,
    requirement_set_id: str,
) -> tuple[AccessCredentialRequirementSet, ...]:
    consumer = AccessConsumerRef(
        consumer_id=f"tool.cli_source:{source.source_id}:{action}",
        module="tool",
        component="cli_source",
        runtime_ref=runtime_ref,
        metadata={
            "provider": config.provider_name,
            "source_id": source.source_id,
        },
    )
    requirements = tuple(
        AccessCredentialRequirementDeclaration(
            requirement_id=f"{source.source_id}.{binding.slot or binding.binding_id}",
            consumer=consumer,
            slot=AccessCredentialSlotRef(
                slot=binding.slot or binding.binding_id,
                expected_kind=binding.expected_kind,
                binding_id=binding.binding_id,
                display_name=binding.display_name,
            ),
            provider=binding.provider,
            transport=AccessCredentialTransport.RUNTIME_CONTEXT,
            parameter_name=binding.env_name or binding.file_env_name,
            metadata={
                "injection": binding.injection,
                "env_name": binding.env_name,
                "file_env_name": binding.file_env_name,
            },
        )
        for binding in config.credential_bindings
    )
    return (
        AccessCredentialRequirementSet(
            requirement_set_id=requirement_set_id,
            consumer=consumer,
            requirements=requirements,
        ),
    )


def _process_output_payload(output: Any) -> dict[str, Any]:
    return {
        "process_id": output.process_id,
        "status": output.status.value,
        "exit_code": output.exit_code,
        "stdout": output.stdout,
        "stderr": output.stderr,
        "stdout_offset": output.stdout_offset,
        "stderr_offset": output.stderr_offset,
        "next_stdout_offset": output.next_stdout_offset,
        "next_stderr_offset": output.next_stderr_offset,
        "started_at": output.started_at.isoformat(),
        "ended_at": output.ended_at.isoformat() if output.ended_at else None,
    }


def _cli_runtime_facts(
    config: CliToolSourceConfig,
    *,
    action: str,
    argv: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "source_id": config.source_id,
        "provider": config.provider_name,
        "cli_action": action,
        "working_directory": str(config.working_directory),
        "shell": config.shell,
        "argv": _sanitized_argv(argv) if argv else (),
        "output_limit_bytes": config.output_limit_bytes,
    }


def _process_continuation_payload(
    output: ProcessOutputWindow,
    *,
    default_limit: int,
) -> dict[str, Any]:
    arguments = {
        "process_id": output.process_id,
        "stdout_offset": output.next_stdout_offset,
        "stderr_offset": output.next_stderr_offset,
        "limit": max(int(default_limit), 1),
    }
    return {
        "tool_action": "cli_read_output",
        "process_id": output.process_id,
        "status": output.status.value,
        "exit_code": output.exit_code,
        "next_read_arguments": arguments,
        "read_hint": (
            "Call cli_read_output with next_read_arguments to continue reading "
            "stdout/stderr for this process."
        ),
    }


def _process_read_handle(
    output: ProcessOutputWindow,
    *,
    default_limit: int,
) -> dict[str, Any]:
    continuation = _process_continuation_payload(
        output,
        default_limit=default_limit,
    )
    return {
        "kind": "tool_call",
        "tool_action": "cli_read_output",
        "process_id": output.process_id,
        "status": output.status.value,
        "exit_code": output.exit_code,
        "arguments": continuation["next_read_arguments"],
    }


def _cli_process_result_envelope(
    details: Mapping[str, Any],
    *,
    source_id: str,
    provider_name: str,
    action: str,
    output: ProcessOutputWindow,
) -> ToolResultEnvelope:
    stdout = str(details.get("stdout") or "")
    stderr = str(details.get("stderr") or "")
    status = _cli_process_envelope_status(output)
    read_handle = _process_read_handle(
        output,
        default_limit=int(details.get("runtime_facts", {}).get("output_limit_bytes") or 4000)
        if isinstance(details.get("runtime_facts"), Mapping)
        else 4000,
    )
    key_facts: dict[str, Any] = {
        "process_id": output.process_id,
        "process_status": output.status.value,
        "exit_code": output.exit_code,
        "stdout_chars": len(stdout),
        "stderr_chars": len(stderr),
        "next_stdout_offset": output.next_stdout_offset,
        "next_stderr_offset": output.next_stderr_offset,
        "working_directory": details.get("working_directory"),
    }
    if stderr.strip():
        key_facts["stderr_preview"] = _short_preview(stderr)
    return ToolResultEnvelope(
        status=status,
        summary=_cli_process_result_summary(
            provider_name=provider_name,
            action=action,
            output=output,
            stdout=stdout,
            stderr=stderr,
        ),
        output_payload=dict(details),
        key_facts=key_facts,
        read_handles=(read_handle,),
        provider_replay_payload={
            "summary": _cli_process_result_summary(
                provider_name=provider_name,
                action=action,
                output=output,
                stdout=stdout,
                stderr=stderr,
            ),
            "process_id": output.process_id,
            "status": output.status.value,
            "exit_code": output.exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "continuation": details.get("continuation"),
            "runtime_facts": details.get("runtime_facts"),
            "read_handles": [read_handle],
        },
        user_summary_payload={
            "summary": _cli_process_result_summary(
                provider_name=provider_name,
                action=action,
                output=output,
                stdout=stdout,
                stderr=stderr,
            ),
            "process_id": output.process_id,
            "status": output.status.value,
            "exit_code": output.exit_code,
        },
        trace_payload={
            "source_id": source_id,
            "provider": provider_name,
            "cli_action": action,
            "process_id": output.process_id,
            "stdout_offset": output.stdout_offset,
            "stderr_offset": output.stderr_offset,
            "next_stdout_offset": output.next_stdout_offset,
            "next_stderr_offset": output.next_stderr_offset,
        },
    )


def _cli_help_result_envelope(
    details: Mapping[str, Any],
    *,
    source_id: str,
    provider_name: str,
) -> ToolResultEnvelope:
    stdout = str(details.get("stdout") or "")
    stderr = str(details.get("stderr") or "")
    exit_code = details.get("exit_code")
    status = "error" if isinstance(exit_code, int) and exit_code != 0 else "ok"
    summary = (
        f"{provider_name} cli_help exited with code {exit_code}."
        if exit_code is not None
        else f"{provider_name} cli_help completed."
    )
    return ToolResultEnvelope(
        status=status,
        summary=summary,
        output_payload=dict(details),
        key_facts={
            "source_id": source_id,
            "provider": provider_name,
            "exit_code": exit_code,
            "stdout_chars": len(stdout),
            "stderr_chars": len(stderr),
            "working_directory": details.get("working_directory"),
        },
        provider_replay_payload={
            "summary": summary,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "runtime_facts": details.get("runtime_facts"),
        },
        user_summary_payload={
            "summary": summary,
            "exit_code": exit_code,
        },
        trace_payload={
            "source_id": source_id,
            "provider": provider_name,
            "cli_action": "cli_help",
        },
    )


def _cli_process_envelope_status(output: ProcessOutputWindow) -> str:
    if output.status.value == "running":
        return "running"
    if output.exit_code not in (None, 0):
        return "error"
    if output.status.value in {"failed", "killed"}:
        return "error"
    return "ok"


def _cli_process_result_summary(
    *,
    provider_name: str,
    action: str,
    output: ProcessOutputWindow,
    stdout: str,
    stderr: str,
) -> str:
    if output.status.value == "running":
        return (
            f"{provider_name} {action} started process {output.process_id}; "
            "read more output with cli_read_output."
        )
    if output.exit_code not in (None, 0):
        preview = _short_preview(stderr or stdout)
        if preview:
            return (
                f"{provider_name} {action} process {output.process_id} exited "
                f"with code {output.exit_code}: {preview}"
            )
        return (
            f"{provider_name} {action} process {output.process_id} exited "
            f"with code {output.exit_code}."
        )
    preview = _short_preview(stdout or stderr)
    if preview:
        return (
            f"{provider_name} {action} process {output.process_id} completed: "
            f"{preview}"
        )
    return (
        f"{provider_name} {action} process {output.process_id} is "
        f"{output.status.value}."
    )


def _short_preview(text: str, *, limit: int = 160) -> str:
    preview = text.strip().replace("\n", " ")
    if len(preview) <= limit:
        return preview
    return f"{preview[: max(limit - 3, 0)]}..."


def _render_cli_output(details: Mapping[str, Any]) -> str:
    stdout = str(details.get("stdout") or "").strip()
    stderr = str(details.get("stderr") or "").strip()
    if stdout and stderr:
        return f"{stdout}\n\nstderr:\n{stderr}"
    return stdout or stderr or f"CLI exited with code {details.get('exit_code')}."


def _cli_output_event_label(stream: str) -> str:
    if stream == "status":
        return "CLI process status"
    return f"CLI {stream}"


def _cli_output_event_summary(
    stream: str,
    text: str,
    output: ProcessOutputWindow,
) -> str:
    if stream == "status":
        if output.exit_code is None:
            return f"CLI process {output.process_id} is {output.status.value}."
        return (
            f"CLI process {output.process_id} ended with exit code "
            f"{output.exit_code}."
        )
    preview = text.strip().replace("\n", " ")
    if len(preview) > 120:
        preview = f"{preview[:117]}..."
    return preview or f"Observed {len(text)} characters on {stream}."


def _cli_output_event_level(
    stream: str,
    output: ProcessOutputWindow,
) -> str:
    if stream == "stderr":
        return "warning"
    if output.exit_code not in {None, 0}:
        return "error"
    return "info"


def _cli_output_event_tone(
    stream: str,
    output: ProcessOutputWindow,
) -> str:
    level = _cli_output_event_level(stream, output)
    if level == "error":
        return "danger"
    if level == "warning":
        return "warning"
    if stream == "status" and output.exit_code == 0:
        return "success"
    return "info"


def _sanitized_argv(argv: tuple[str, ...]) -> list[str]:
    return list(argv)


def _credential_injection_metadata(
    binding: CliCredentialBindingConfig,
) -> dict[str, str | None]:
    return {
        "binding_id": binding.binding_id,
        "injection": binding.injection,
        "env_name": binding.env_name,
        "file_env_name": binding.file_env_name,
        "file_name": binding.file_name if binding.injection == "file" else None,
        "expected_kind": binding.expected_kind.value,
        "provider": binding.provider,
        "slot": binding.slot,
    }


def _redact_cli_output(text: str, redactions: tuple[str, ...]) -> str:
    redacted = text
    for secret in sorted(set(redactions), key=len, reverse=True):
        if not secret:
            continue
        redacted = redacted.replace(secret, "[credential:redacted]")
    return redacted


def _write_credential_temp_file(secret: str, *, file_name: str) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="crxzipple-tool-credential-"))
    os.chmod(temp_dir, 0o700)
    path = temp_dir / _safe_credential_file_name(file_name)
    path.write_text(secret, encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def _safe_credential_file_name(value: str) -> str:
    normalized = "".join(
        ch
        for ch in value.strip()
        if ch.isalnum() or ch in {"-", "_", "."}
    ).strip(".")
    return normalized or "credential"


def _process_env(env: Mapping[str, str]) -> dict[str, str] | None:
    if not env:
        return None
    process_env = dict(os.environ)
    process_env.update(env)
    return process_env


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"


def _safe_tool_id(value: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")
    normalized = "_".join(part for part in normalized.split("_") if part)
    if len(normalized) <= 56:
        return normalized or "cli_source"
    return normalized[:56].rstrip("_")


def _text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(
        dict.fromkeys(
            str(item).strip()
            for item in value
            if str(item).strip()
        ),
    )


def _argv_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ToolValidationError(f"CLI source field '{field_name}' must be a list.")
    resolved: list[str] = []
    for index, item in enumerate(value):
        text = str(item).strip()
        if not text:
            raise ToolValidationError(
                f"CLI source field '{field_name}[{index}]' cannot be empty.",
            )
        resolved.append(text)
    return tuple(resolved)


def _mapping_tuple(value: object, *, field_name: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ToolValidationError(f"CLI source field '{field_name}' must be a list.")
    items: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ToolValidationError(
                f"CLI source field '{field_name}[{index}]' must be an object.",
            )
        items.append(item)
    return tuple(items)


def _credential_binding_configs(
    value: object,
    *,
    source_id: str,
) -> tuple[CliCredentialBindingConfig, ...]:
    configs: list[CliCredentialBindingConfig] = []
    for index, item in enumerate(
        _mapping_tuple(value, field_name=f"{source_id}.provider.credential_bindings"),
    ):
        injection = _optional_text(item.get("injection")) or "env"
        if injection not in CLI_CREDENTIAL_INJECTION_KINDS:
            allowed = ", ".join(sorted(CLI_CREDENTIAL_INJECTION_KINDS))
            raise ToolValidationError(
                f"CLI credential injection must be one of: {allowed}.",
            )
        binding_id = _required_text(
            item.get("binding_id"),
            field_name=f"{source_id}.provider.credential_bindings[{index}].binding_id",
        )
        if item.get("credential_binding_id") is not None:
            raise ToolValidationError(
                f"{source_id}.provider.credential_bindings[{index}] must use binding_id; "
                "field 'credential_binding_id' is no longer accepted.",
            )
        _reject_direct_credential_binding_source(
            binding_id,
            source_id=source_id,
            index=index,
        )
        env_name = _optional_text(item.get("env_name"))
        file_env_name = _optional_text(item.get("file_env_name"))
        if injection == "env" and env_name is None:
            raise ToolValidationError(
                f"CLI credential binding '{binding_id}' requires env_name for env injection.",
            )
        if injection == "file" and file_env_name is None:
            raise ToolValidationError(
                f"CLI credential binding '{binding_id}' requires file_env_name for file injection.",
            )
        configs.append(
            CliCredentialBindingConfig(
                binding_id=binding_id,
                injection=injection,
                env_name=env_name,
                file_env_name=file_env_name,
                file_name=_optional_text(item.get("file_name")) or "credential",
                expected_kind=_credential_kind(item.get("expected_kind")),
                provider=_optional_text(item.get("provider")),
                slot=_optional_text(item.get("slot")),
                display_name=_optional_text(item.get("display_name")),
            ),
        )
    return tuple(configs)


def _reject_direct_credential_binding_source(
    binding_id: str,
    *,
    source_id: str,
    index: int,
) -> None:
    normalized = binding_id.strip()
    if normalized.startswith(_FORBIDDEN_DIRECT_CREDENTIAL_SOURCE_PREFIXES):
        raise ToolValidationError(
            f"{source_id}.provider.credential_bindings[{index}].binding_id must "
            "reference an Access credential binding id, not a direct credential source.",
        )


def _promoted_function_configs(
    value: object,
    *,
    source_id: str,
) -> tuple[CliPromotedFunctionConfig, ...]:
    configs: list[CliPromotedFunctionConfig] = []
    for index, item in enumerate(
        _mapping_tuple(value, field_name=f"{source_id}.provider.promoted_functions"),
    ):
        function_id = _safe_promoted_id(
            _required_text(
                item.get("id") or item.get("function_id"),
                field_name=f"{source_id}.provider.promoted_functions[{index}].id",
            ),
        )
        raw_args = item.get("args")
        if raw_args is None:
            raw_args = item.get("argv")
        args = _argv_tuple(
            raw_args,
            field_name=f"{source_id}.provider.promoted_functions[{index}].args",
        )
        parameters = _promoted_parameter_configs(
            item.get("parameters"),
            args=args,
            field_name=f"{source_id}.provider.promoted_functions[{index}].parameters",
        )
        configs.append(
            CliPromotedFunctionConfig(
                function_id=function_id,
                name=_required_text(
                    item.get("name"),
                    field_name=f"{source_id}.provider.promoted_functions[{index}].name",
                ),
                description=_required_text(
                    item.get("description"),
                    field_name=(
                        f"{source_id}.provider.promoted_functions[{index}].description"
                    ),
                ),
                subcommand=_required_text(
                    item.get("subcommand"),
                    field_name=(
                        f"{source_id}.provider.promoted_functions[{index}].subcommand"
                    ),
                ),
                args=args,
                parameters=parameters,
                initial_output_limit=_optional_positive_int(
                    item.get("initial_output_limit"),
                ),
                mutates_state=_bool(item.get("mutates_state"), default=False),
                required_effect_ids=_text_tuple(item.get("required_effect_ids")),
            ),
        )
    _ensure_unique_promoted_functions(configs, source_id=source_id)
    return tuple(configs)


def _promoted_parameter_configs(
    value: object,
    *,
    args: tuple[str, ...],
    field_name: str,
) -> tuple[CliPromotedFunctionParameterConfig, ...]:
    explicit = _mapping_tuple(value, field_name=field_name)
    if not explicit:
        return tuple(
            CliPromotedFunctionParameterConfig(name=name)
            for name in _promoted_placeholders(args)
        )
    parameters: list[CliPromotedFunctionParameterConfig] = []
    for index, item in enumerate(explicit):
        parameters.append(
            CliPromotedFunctionParameterConfig(
                name=_safe_parameter_name(
                    _required_text(
                        item.get("name"),
                        field_name=f"{field_name}[{index}].name",
                    ),
                ),
                data_type=_optional_text(item.get("data_type")) or "string",
                description=_optional_text(item.get("description")) or "",
                required=_bool(item.get("required"), default=True),
            ),
        )
    _ensure_unique_promoted_parameters(parameters, field_name=field_name)
    return tuple(parameters)


def _promoted_placeholders(args: tuple[str, ...]) -> tuple[str, ...]:
    names: list[str] = []
    for template in args:
        names.extend(PROMOTED_ARG_PATTERN.findall(template))
    return tuple(dict.fromkeys(names))


def _promoted_argument_value(
    arguments: Mapping[str, Any],
    name: str,
    *,
    parameters: tuple[CliPromotedFunctionParameterConfig, ...],
    embedded: bool,
) -> Any:
    parameter = next(
        (candidate for candidate in parameters if candidate.name == name),
        None,
    )
    required = parameter.required if parameter is not None else True
    value = arguments.get(name)
    if value is None or value == "":
        if required or embedded:
            raise ToolValidationError(
                f"CLI promoted function argument '{name}' is required.",
            )
        return None
    return value


def _promoted_scalar_text(value: object, name: str) -> str:
    if isinstance(value, dict):
        raise ToolValidationError(
            f"CLI promoted function argument '{name}' must be a scalar or array.",
        )
    text = str(value).strip()
    if not text:
        raise ToolValidationError(
            f"CLI promoted function argument '{name}' cannot be empty.",
        )
    return text


def _ensure_unique_promoted_functions(
    configs: list[CliPromotedFunctionConfig],
    *,
    source_id: str,
) -> None:
    ids = [config.function_id for config in configs]
    if len(ids) != len(set(ids)):
        raise ToolValidationError(
            f"Configured CLI source '{source_id}' has duplicate promoted function ids.",
        )


def _ensure_unique_promoted_parameters(
    parameters: list[CliPromotedFunctionParameterConfig],
    *,
    field_name: str,
) -> None:
    names = [parameter.name for parameter in parameters]
    if len(names) != len(set(names)):
        raise ToolValidationError(
            f"CLI source field '{field_name}' has duplicate parameter names.",
        )


def _credential_kind(value: object) -> AccessCredentialKind:
    raw = _optional_text(value) or AccessCredentialKind.API_KEY.value
    try:
        return AccessCredentialKind(raw)
    except ValueError as exc:
        raise ToolValidationError(
            f"CLI credential expected_kind '{raw}' is not supported.",
        ) from exc


def _bool(value: object, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ToolValidationError("CLI source boolean policy values must be booleans.")


def _safe_promoted_id(value: str) -> str:
    normalized = _safe_tool_id(value)
    if not normalized:
        raise ToolValidationError("CLI promoted function id cannot be empty.")
    return normalized


def _safe_parameter_name(value: str) -> str:
    normalized = value.strip()
    if not PROMOTED_ARG_PATTERN.fullmatch(f"{{{normalized}}}"):
        raise ToolValidationError(
            f"CLI promoted parameter name '{value}' is invalid.",
        )
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _required_text(value: object, *, field_name: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ToolValidationError(f"CLI source field '{field_name}' is required.")
    return normalized


def _positive_int(value: object, *, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolValidationError("CLI source numeric policy values must be integers.") from exc
    if resolved < 1:
        raise ToolValidationError("CLI source numeric policy values must be positive.")
    return resolved


def _optional_positive_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return _positive_int(value, default=1)


def _non_negative_int(value: object) -> int:
    if value is None or value == "":
        return 0
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolValidationError("CLI source offsets must be integers.") from exc
    if resolved < 0:
        raise ToolValidationError("CLI source offsets cannot be negative.")
    return resolved


def _resolve_executable(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ToolValidationError("CLI executable cannot be empty.")
    if "/" in normalized:
        return str(Path(normalized).expanduser().resolve())
    return normalized


def _resolve_directory(
    value: object,
    *,
    default: Path,
    field_name: str,
) -> Path:
    raw = _optional_text(value)
    path = Path(raw).expanduser() if raw is not None else default
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ToolValidationError(f"CLI source directory '{field_name}' does not exist.")
    return resolved


def _ensure_path_in_roots(
    path: Path,
    *,
    allowed_roots: tuple[Path, ...],
    field_name: str,
) -> None:
    resolved = path.resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(root.resolve())
            return
        except ValueError:
            continue
    roots = ", ".join(str(root) for root in allowed_roots)
    raise ToolValidationError(
        f"CLI source {field_name} '{resolved}' is outside allowed roots: {roots}.",
    )


__all__ = [
    "CliToolSourceConfig",
    "discover_cli_source",
    "register_cli_guided_handlers",
]
