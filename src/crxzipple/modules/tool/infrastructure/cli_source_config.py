from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import os
import shutil
from typing import Any

from crxzipple.modules.tool.application.catalog_models import ToolSourceCatalogRecord
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.cli_source_config_credentials import (
    CliCredentialBindingConfig,
    credential_binding_configs,
)
from crxzipple.modules.tool.infrastructure.cli_source_config_promoted import (
    CliPromotedFunctionConfig,
    CliPromotedFunctionParameterConfig,
    promoted_function_configs,
)
from crxzipple.modules.tool.infrastructure.cli_source_config_values import (
    optional_positive_int,
    optional_text,
    positive_int,
    required_text,
    text_tuple,
)
from crxzipple.modules.tool.infrastructure.cli_source_paths import (
    ensure_path_in_roots,
    resolve_directory,
    resolve_executable,
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
            credential_bindings=credential_binding_configs(
                provider.get("credential_bindings"),
                source_id=source.source_id,
            ),
            promoted_functions=promoted_function_configs(
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

__all__ = [
    "CliCredentialBindingConfig",
    "CliPromotedFunctionConfig",
    "CliPromotedFunctionParameterConfig",
    "CliToolSourceConfig",
]
