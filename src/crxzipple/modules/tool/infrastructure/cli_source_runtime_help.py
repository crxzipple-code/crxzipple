from __future__ import annotations

import asyncio
from collections.abc import Mapping
import os
import subprocess
from typing import Any

from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)
from crxzipple.modules.tool.domain import ToolRunResult
from crxzipple.modules.tool.infrastructure.cli_source_config import (
    CliToolSourceConfig,
)
from crxzipple.modules.tool.infrastructure.cli_source_config_values import (
    optional_text,
)
from crxzipple.modules.tool.infrastructure.cli_source_credentials import (
    resolve_credential_injection,
)
from crxzipple.modules.tool.infrastructure.cli_source_envelopes import (
    cli_help_result_envelope,
    cli_runtime_facts,
    render_cli_output,
    sanitized_argv,
)


async def run_cli_help(
    config: CliToolSourceConfig,
    arguments: Mapping[str, Any],
    *,
    credential_provider: Any | None,
) -> ToolRunResult:
    subcommand = optional_text(arguments.get("subcommand"))
    argv = config.build_help_argv(subcommand=subcommand)
    injection = resolve_credential_injection(
        config,
        credential_provider=credential_provider,
        action="cli_help",
    )
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            list(argv),
            cwd=str(config.working_directory),
            text=True,
            capture_output=True,
            timeout=config.timeout_seconds,
            check=False,
            env=_process_env(injection.env),
        )
        details = {
            "argv": sanitized_argv(argv),
            "exit_code": completed.returncode,
            "stdout": _truncate(completed.stdout, config.output_limit_bytes),
            "stderr": _truncate(completed.stderr, config.output_limit_bytes),
            "working_directory": str(config.working_directory),
            "credential_injections": injection.metadata,
            "runtime_facts": cli_runtime_facts(
                config,
                action="cli_help",
                argv=argv,
            ),
        }
        return ToolRunResult.text(
            render_cli_output(details),
            details=details,
            metadata={
                "source_id": config.source_id,
                "provider": config.provider_name,
                "cli_action": "cli_help",
                TOOL_RESULT_ENVELOPE_METADATA_KEY: cli_help_result_envelope(
                    details,
                    source_id=config.source_id,
                    provider_name=config.provider_name,
                ).to_payload(),
            },
        )
    finally:
        injection.cleanup()


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


__all__ = ["run_cli_help"]
