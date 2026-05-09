from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from crxzipple.interfaces.authorization import authorize_tool_run
from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.tool.application import (
    ExecuteToolInput,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolMode,
)
from crxzipple.modules.tool.interfaces.dto import (
    ToolDTO,
    ToolDiscoveryProviderDTO,
    ToolRunDTO,
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
    app = typer.Typer(help="Inspect tools and tool runs.", no_args_is_help=True)

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

    @app.command("roots")
    def list_tool_roots(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        echo_data(
            [
                {
                    "path": path,
                    "exists": Path(path).exists(),
                }
                for path in container.tool_bootstrap_config.local_paths
            ],
        )

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
