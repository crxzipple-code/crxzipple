from __future__ import annotations

from crxzipple.modules.tool.domain import (
    ToolExecutionPolicy,
    ToolParameter,
)
from crxzipple.modules.tool.infrastructure.cli_source_config import (
    CliPromotedFunctionConfig,
    CliToolSourceConfig,
)


GUIDED_CLI_ACTIONS: tuple[str, ...] = (
    "cli_help",
    "cli_execute",
    "cli_read_output",
    "cli_cancel",
)


def guided_cli_name(config: CliToolSourceConfig, action: str) -> str:
    label = action.removeprefix("cli_").replace("_", " ").title()
    return f"{config.provider_name} {label}"


def guided_cli_description(config: CliToolSourceConfig, action: str) -> str:
    if action == "cli_help":
        return f"Read help output from configured CLI source '{config.provider_name}'."
    if action == "cli_execute":
        return f"Start a governed command for configured CLI source '{config.provider_name}'."
    if action == "cli_read_output":
        return f"Read stdout/stderr from a governed CLI process for '{config.provider_name}'."
    if action == "cli_cancel":
        return f"Cancel a governed CLI process for '{config.provider_name}'."
    return f"Run guided CLI action '{action}' for '{config.provider_name}'."


def guided_cli_parameters(action: str) -> tuple[ToolParameter, ...]:
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
            ToolParameter(
                name="process_id",
                data_type="string",
                description="Process session id.",
            ),
            ToolParameter(name="stdout_offset", data_type="integer", required=False),
            ToolParameter(name="stderr_offset", data_type="integer", required=False),
            ToolParameter(name="limit", data_type="integer", required=False),
        )
    if action == "cli_cancel":
        return (
            ToolParameter(
                name="process_id",
                data_type="string",
                description="Process session id.",
            ),
        )
    return ()


def guided_cli_effects(
    config: CliToolSourceConfig,
    action: str,
) -> tuple[str, ...]:
    if action == "cli_execute" and config.mutating_subcommands:
        return ("tool.cli.mutate",)
    if action == "cli_cancel":
        return ("tool.cli.cancel",)
    return ()


def guided_cli_policy(
    config: CliToolSourceConfig,
    action: str,
) -> ToolExecutionPolicy:
    mutates = action == "cli_execute" and bool(config.mutating_subcommands)
    return ToolExecutionPolicy(
        timeout_seconds=config.timeout_seconds,
        requires_confirmation=mutates or action == "cli_cancel",
        mutates_state=mutates or action == "cli_cancel",
    )


def promoted_cli_effects(
    config: CliToolSourceConfig,
    promoted: CliPromotedFunctionConfig,
) -> tuple[str, ...]:
    if promoted.required_effect_ids:
        return promoted.required_effect_ids
    if promoted.mutates_state or promoted.subcommand in config.mutating_subcommands:
        return ("tool.cli.mutate",)
    return ()


def promoted_cli_policy(
    config: CliToolSourceConfig,
    promoted: CliPromotedFunctionConfig,
) -> ToolExecutionPolicy:
    mutates = promoted.mutates_state or promoted.subcommand in config.mutating_subcommands
    return ToolExecutionPolicy(
        timeout_seconds=config.timeout_seconds,
        requires_confirmation=mutates,
        mutates_state=mutates,
    )


__all__ = [
    "GUIDED_CLI_ACTIONS",
    "guided_cli_description",
    "guided_cli_effects",
    "guided_cli_name",
    "guided_cli_parameters",
    "guided_cli_policy",
    "promoted_cli_effects",
    "promoted_cli_policy",
]
