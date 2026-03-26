from __future__ import annotations

import asyncio
import json

import typer

from crxzipple.interfaces.authorization import authorize_tool_run
from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.tool.application import (
    ExecuteToolInput,
    RegisterToolInput,
    RegisterToolParameterInput,
    SetToolAvailabilityInput,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolSourceKind,
)
from crxzipple.modules.tool.interfaces.dto import (
    ToolDTO,
    ToolDiscoveryProviderDTO,
    ToolRunDTO,
)


def _parse_parameter(definition: str, *, required: bool) -> RegisterToolParameterInput:
    parts = definition.split(":", 2)
    if len(parts) < 2:
        raise typer.BadParameter(
            "Parameter definitions must use name:type[:description].",
        )

    name, data_type = parts[0].strip(), parts[1].strip()
    description = parts[2].strip() if len(parts) == 3 else ""
    return RegisterToolParameterInput(
        name=name,
        data_type=data_type,
        description=description,
        required=required,
    )


def _parse_json_object(payload: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("Input must be a valid JSON object.") from exc

    if not isinstance(value, dict):
        raise typer.BadParameter("Input must decode to a JSON object.")
    return value


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage tools.", no_args_is_help=True)

    @app.command("register")
    def register_tool(
        ctx: typer.Context,
        tool_id: str = typer.Argument(..., help="Tool identifier."),
        name: str = typer.Argument(..., help="Display name."),
        description: str = typer.Argument(..., help="Tool description."),
        kind: ToolKind = typer.Option(ToolKind.FUNCTION, "--kind", help="Tool kind."),
        parameter: list[str] | None = typer.Option(
            None,
            "--parameter",
            help="Required parameter as name:type[:description].",
        ),
        optional_parameter: list[str] | None = typer.Option(
            None,
            "--optional-parameter",
            help="Optional parameter as name:type[:description].",
        ),
        tag: list[str] | None = typer.Option(None, "--tag", help="Tool classification tag."),
        required_effect: list[str] | None = typer.Option(
            None,
            "--required-effect",
            help="Required shared effect id. Repeat to declare multiple values.",
        ),
        timeout_seconds: int = typer.Option(
            30,
            "--timeout-seconds",
            min=1,
            help="Tool execution timeout in seconds.",
        ),
        requires_confirmation: bool = typer.Option(
            False,
            "--requires-confirmation/--no-requires-confirmation",
            help="Whether using the tool needs a user confirmation gate.",
        ),
        mutates_state: bool = typer.Option(
            False,
            "--mutates-state/--read-only",
            help="Whether the tool changes external state.",
        ),
        mode: list[ToolMode] | None = typer.Option(
            None,
            "--mode",
            help="Supported execution mode. Repeat to allow multiple values.",
        ),
        strategy: list[ToolExecutionStrategy] | None = typer.Option(
            None,
            "--strategy",
            help="Supported execution strategy. Repeat to allow multiple values.",
        ),
        environment: list[ToolEnvironment] | None = typer.Option(
            None,
            "--environment",
            help="Supported execution environment. Repeat to allow multiple values.",
        ),
        source_kind: ToolSourceKind = typer.Option(
            ToolSourceKind.MANUAL,
            "--source-kind",
            help="How this tool definition was registered.",
        ),
        runtime_key: str | None = typer.Option(
            None,
            "--runtime-key",
            help="Executor-specific runtime binding.",
        ),
        enabled: bool = typer.Option(True, "--enabled/--disabled"),
    ) -> None:
        container = ensure_container(ctx)
        parameters = [
            _parse_parameter(item, required=True) for item in parameter or []
        ] + [
            _parse_parameter(item, required=False)
            for item in optional_parameter or []
        ]
        tool = container.tool_service.register(
            RegisterToolInput(
                id=tool_id,
                name=name,
                description=description,
                kind=kind,
                parameters=tuple(parameters),
                tags=tuple(tag or []),
                required_effect_ids=tuple(required_effect or []),
                timeout_seconds=timeout_seconds,
                requires_confirmation=requires_confirmation,
                mutates_state=mutates_state,
                supported_modes=tuple(mode or [ToolMode.INLINE]),
                supported_strategies=tuple(
                    strategy or [ToolExecutionStrategy.ASYNC],
                ),
                supported_environments=tuple(
                    environment or [ToolEnvironment.LOCAL],
                ),
                source_kind=source_kind,
                runtime_key=runtime_key,
                enabled=enabled,
            ),
        )
        echo_data(ToolDTO.from_entity(tool))

    @app.command("list")
    def list_tools(
        ctx: typer.Context,
        enabled_only: bool = typer.Option(
            False,
            "--enabled-only",
            help="List only enabled tools.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        tools = (
            container.tool_service.list_enabled_tools()
            if enabled_only
            else container.tool_service.list_tools()
        )
        items = [ToolDTO.from_entity(tool) for tool in tools]
        echo_data(items)

    @app.command("enable")
    def enable_tool(
        ctx: typer.Context,
        tool_id: str = typer.Argument(..., help="Tool identifier."),
    ) -> None:
        container = ensure_container(ctx)
        tool = container.tool_service.set_availability(
            SetToolAvailabilityInput(id=tool_id, enabled=True),
        )
        echo_data(ToolDTO.from_entity(tool))

    @app.command("disable")
    def disable_tool(
        ctx: typer.Context,
        tool_id: str = typer.Argument(..., help="Tool identifier."),
    ) -> None:
        container = ensure_container(ctx)
        tool = container.tool_service.set_availability(
            SetToolAvailabilityInput(id=tool_id, enabled=False),
        )
        echo_data(ToolDTO.from_entity(tool))

    @app.command("discover-local")
    def discover_local_tools(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        tools = container.tool_service.discover_local_tools()
        echo_data([ToolDTO.from_entity(tool) for tool in tools])

    @app.command("providers")
    def list_discovery_providers(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        providers = container.tool_service.list_discovery_providers()
        echo_data(
            [
                ToolDiscoveryProviderDTO.from_descriptor(provider)
                for provider in providers
            ],
        )

    @app.command("discover")
    def discover_tools(
        ctx: typer.Context,
        provider: str | None = typer.Option(
            None,
            "--provider",
            help="Optional discovery provider name.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        tools = container.tool_service.discover_tools(provider_name=provider)
        echo_data([ToolDTO.from_entity(tool) for tool in tools])

    @app.command("run")
    def run_tool(
        ctx: typer.Context,
        tool_id: str = typer.Argument(..., help="Tool identifier."),
        input_payload: str = typer.Option(
            "{}",
            "--input",
            help="JSON object passed to the tool runtime.",
        ),
        mode: ToolMode = typer.Option(
            ToolMode.INLINE,
            "--mode",
            help="Execution mode for this run.",
        ),
        strategy: ToolExecutionStrategy = typer.Option(
            ToolExecutionStrategy.ASYNC,
            "--strategy",
            help="Execution strategy for this run.",
        ),
        environment: ToolEnvironment = typer.Option(
            ToolEnvironment.LOCAL,
            "--environment",
            help="Execution environment for this run.",
        ),
        run_id: str | None = typer.Option(
            None,
            "--run-id",
            help="Optional caller-provided run id.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        authorize_tool_run(
            container,
            tool_id=tool_id,
            mode=mode,
            strategy=strategy,
            environment=environment,
            interface_name="cli",
        )
        tool_run = asyncio.run(
            container.tool_service.execute(
                ExecuteToolInput(
                    tool_id=tool_id,
                    arguments=_parse_json_object(input_payload),
                    mode=mode,
                    strategy=strategy,
                    environment=environment,
                    run_id=run_id,
                ),
            ),
        )
        echo_data(ToolRunDTO.from_entity(tool_run))

    @app.command("runs")
    def list_tool_runs(
        ctx: typer.Context,
        tool_id: str | None = typer.Option(
            None,
            "--tool-id",
            help="Filter runs for a single tool.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        runs = container.tool_service.list_tool_runs(tool_id=tool_id)
        echo_data([ToolRunDTO.from_entity(run) for run in runs])

    @app.command("get-run")
    def get_tool_run(
        ctx: typer.Context,
        run_id: str = typer.Argument(..., help="Tool run identifier."),
    ) -> None:
        container = ensure_container(ctx)
        tool_run = container.tool_service.get_tool_run(run_id)
        echo_data(ToolRunDTO.from_entity(tool_run))

    @app.command("cancel-run")
    def cancel_tool_run(
        ctx: typer.Context,
        run_id: str = typer.Argument(..., help="Tool run identifier."),
    ) -> None:
        container = ensure_container(ctx)
        tool_run = container.tool_service.cancel_tool_run(run_id)
        echo_data(ToolRunDTO.from_entity(tool_run))

    return app
