from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
from typing import Any

from crxzipple.modules.tool.application.catalog_models import ToolSourceCatalogRecord
from crxzipple.modules.tool.application.specifications import ToolParameter
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.cli_source_config_values import (
    argv_tuple,
    bool_value,
    mapping_tuple,
    optional_positive_int,
    optional_text,
    positive_int,
    required_text,
    safe_tool_id,
    text_tuple,
)
from crxzipple.modules.tool.infrastructure.cli_source_paths import (
    ensure_path_in_roots,
    resolve_directory,
    resolve_executable,
)
from crxzipple.shared.access import AccessCredentialKind


CLI_CREDENTIAL_INJECTION_KINDS = frozenset({"env", "file"})
PROMOTED_ARG_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
FORBIDDEN_DIRECT_CREDENTIAL_SOURCE_PREFIXES = (
    "env:",
    "file:",
    "codex_auth_json",
    "codex-cli",
    "auth_ref",
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

        command = text_tuple(provider.get("command"))
        executable = optional_text(provider.get("executable"))
        base_args = text_tuple(provider.get("base_args"))
        if executable is None and command:
            executable = command[0]
            base_args = command[1:]
        if executable is None:
            raise ToolValidationError(
                f"Configured CLI source '{source.source_id}' requires config.provider.executable or command.",
            )

        provider_name = required_text(
            provider.get("name"),
            field_name=f"{source.source_id}.provider.name",
        )
        working_directory = resolve_directory(
            provider.get("working_directory"),
            default=Path.cwd(),
            field_name=f"{source.source_id}.provider.working_directory",
        )
        allowed_roots = tuple(
            resolve_directory(
                root,
                default=working_directory,
                field_name=f"{source.source_id}.provider.allowed_roots",
            )
            for root in text_tuple(provider.get("allowed_roots"))
        ) or (working_directory,)
        ensure_path_in_roots(
            working_directory,
            allowed_roots=allowed_roots,
            field_name="working_directory",
        )

        config = cls(
            source_id=source.source_id,
            provider_name=provider_name,
            executable=resolve_executable(executable),
            base_args=base_args,
            allowed_subcommands=text_tuple(provider.get("allowed_subcommands")),
            denied_flags=text_tuple(provider.get("denied_flags")),
            mutating_subcommands=text_tuple(provider.get("mutating_subcommands")),
            help_args=(text_tuple(provider.get("help_args")) or ("--help",)),
            working_directory=working_directory,
            allowed_roots=allowed_roots,
            timeout_seconds=positive_int(
                provider.get("timeout_seconds"),
                default=30,
            ),
            output_limit_bytes=positive_int(
                provider.get("output_limit_bytes"),
                default=16000,
            ),
            shell=optional_text(provider.get("shell")) or "/bin/zsh",
            max_concurrency=optional_positive_int(provider.get("max_concurrency")),
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
            ensure_path_in_roots(
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


def _credential_binding_configs(
    value: object,
    *,
    source_id: str,
) -> tuple[CliCredentialBindingConfig, ...]:
    configs: list[CliCredentialBindingConfig] = []
    for index, item in enumerate(
        mapping_tuple(value, field_name=f"{source_id}.provider.credential_bindings"),
    ):
        injection = optional_text(item.get("injection")) or "env"
        if injection not in CLI_CREDENTIAL_INJECTION_KINDS:
            allowed = ", ".join(sorted(CLI_CREDENTIAL_INJECTION_KINDS))
            raise ToolValidationError(
                f"CLI credential injection must be one of: {allowed}.",
            )
        binding_id = required_text(
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
        env_name = optional_text(item.get("env_name"))
        file_env_name = optional_text(item.get("file_env_name"))
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
                file_name=optional_text(item.get("file_name")) or "credential",
                expected_kind=_credential_kind(item.get("expected_kind")),
                provider=optional_text(item.get("provider")),
                slot=optional_text(item.get("slot")),
                display_name=optional_text(item.get("display_name")),
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
    if normalized.startswith(FORBIDDEN_DIRECT_CREDENTIAL_SOURCE_PREFIXES):
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
        mapping_tuple(value, field_name=f"{source_id}.provider.promoted_functions"),
    ):
        function_id = _safe_promoted_id(
            required_text(
                item.get("id") or item.get("function_id"),
                field_name=f"{source_id}.provider.promoted_functions[{index}].id",
            ),
        )
        raw_args = item.get("args")
        if raw_args is None:
            raw_args = item.get("argv")
        args = argv_tuple(
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
                name=required_text(
                    item.get("name"),
                    field_name=f"{source_id}.provider.promoted_functions[{index}].name",
                ),
                description=required_text(
                    item.get("description"),
                    field_name=(
                        f"{source_id}.provider.promoted_functions[{index}].description"
                    ),
                ),
                subcommand=required_text(
                    item.get("subcommand"),
                    field_name=(
                        f"{source_id}.provider.promoted_functions[{index}].subcommand"
                    ),
                ),
                args=args,
                parameters=parameters,
                initial_output_limit=optional_positive_int(
                    item.get("initial_output_limit"),
                ),
                mutates_state=bool_value(item.get("mutates_state"), default=False),
                required_effect_ids=text_tuple(item.get("required_effect_ids")),
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
    explicit = mapping_tuple(value, field_name=field_name)
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
                    required_text(
                        item.get("name"),
                        field_name=f"{field_name}[{index}].name",
                    ),
                ),
                data_type=optional_text(item.get("data_type")) or "string",
                description=optional_text(item.get("description")) or "",
                required=bool_value(item.get("required"), default=True),
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
    raw = optional_text(value) or AccessCredentialKind.API_KEY.value
    try:
        return AccessCredentialKind(raw)
    except ValueError as exc:
        raise ToolValidationError(
            f"CLI credential expected_kind '{raw}' is not supported.",
        ) from exc


def _safe_promoted_id(value: str) -> str:
    normalized = safe_tool_id(value)
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


__all__ = [
    "CliCredentialBindingConfig",
    "CliPromotedFunctionConfig",
    "CliPromotedFunctionParameterConfig",
    "CliToolSourceConfig",
]
