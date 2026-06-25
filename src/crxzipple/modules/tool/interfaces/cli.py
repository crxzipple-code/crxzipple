from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from crxzipple.interfaces.authorization import authorize_tool_run
from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.tool.application import (
    ExecuteToolInput,
    ToolSourceCatalogRecord,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolMode,
)
from crxzipple.modules.tool.interfaces.dto import (
    ToolDTO,
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


def _parse_text_tuple(payload: str | None) -> tuple[str, ...]:
    if payload is None:
        return ()
    return tuple(
        dict.fromkeys(
            item.strip()
            for item in payload.split(",")
            if item.strip()
        ),
    )


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
            container.require(AppKey.TOOL_SERVICE).list_enabled_tools()
            if enabled_only
            else container.require(AppKey.TOOL_SERVICE).list_tools()
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
                for path in container.require(AppKey.TOOL_BOOTSTRAP_CONFIG).local_paths
            ],
        )

    @app.command("sources")
    def list_tool_sources(
        ctx: typer.Context,
        kind: str | None = typer.Option(None, "--kind"),
        status: str | None = typer.Option(None, "--status"),
    ) -> None:
        container = ensure_container(ctx)
        sources = container.require(AppKey.TOOL_SOURCE_QUERY_SERVICE).list_sources(
            kind=kind,
            status=status,
        )
        echo_data(sources)

    @app.command("source-create")
    def create_tool_source(
        ctx: typer.Context,
        source_id: str = typer.Argument(..., help="Tool source identifier."),
        kind: str = typer.Option(..., "--kind", help="Source kind: openapi or mcp."),
        display_name: str = typer.Option(..., "--display-name"),
        config: str = typer.Option(
            "{}",
            "--config",
            help="Source config JSON object owned by Tool.",
        ),
        description: str = typer.Option("", "--description"),
        runtime_requirements: str | None = typer.Option(
            None,
            "--runtime-requirements",
            help="Comma-separated runtime requirements.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        result = container.require(AppKey.TOOL_SOURCE_COMMAND_SERVICE).create_source(
            ToolSourceCatalogRecord(
                source_id=source_id,
                kind=kind,
                display_name=display_name,
                description=description,
                config=_parse_json_object(config),
                runtime_requirements=_parse_text_tuple(runtime_requirements),
            ),
        )
        echo_data(result)

    @app.command("source-update")
    def update_tool_source(
        ctx: typer.Context,
        source_id: str = typer.Argument(..., help="Tool source identifier."),
        kind: str = typer.Option(..., "--kind", help="Source kind: openapi or mcp."),
        display_name: str = typer.Option(..., "--display-name"),
        config: str = typer.Option(
            "{}",
            "--config",
            help="Replacement source config JSON object owned by Tool.",
        ),
        description: str = typer.Option("", "--description"),
        runtime_requirements: str | None = typer.Option(
            None,
            "--runtime-requirements",
            help="Comma-separated runtime requirements.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        result = container.require(AppKey.TOOL_SOURCE_COMMAND_SERVICE).update_source(
            source_id,
            ToolSourceCatalogRecord(
                source_id=source_id,
                kind=kind,
                display_name=display_name,
                description=description,
                config=_parse_json_object(config),
                runtime_requirements=_parse_text_tuple(runtime_requirements),
            ),
        )
        echo_data(result)

    @app.command("source-history")
    def list_tool_source_history(
        ctx: typer.Context,
        source_id: str = typer.Argument(..., help="Tool source identifier."),
        limit: int = typer.Option(20, "--limit"),
    ) -> None:
        container = ensure_container(ctx)
        runs = container.require(
            AppKey.TOOL_SOURCE_QUERY_SERVICE,
        ).list_discovery_runs(source_id, limit=limit)
        echo_data(runs)

    @app.command("source-refresh")
    def refresh_tool_source(
        ctx: typer.Context,
        source_id: str = typer.Argument(..., help="Tool source identifier."),
    ) -> None:
        container = ensure_container(ctx)
        source = container.require(AppKey.TOOL_SOURCE_QUERY_SERVICE).get_source(source_id)
        if source is None:
            raise typer.BadParameter(f"Tool source '{source_id}' was not found.")
        result = container.require(AppKey.TOOL_SOURCE_COMMAND_SERVICE).sync_source(
            source,
            discovery_service=container.require(AppKey.TOOL_SOURCE_DISCOVERY_SERVICE),
        )
        echo_data(_source_sync_payload(result))

    @app.command("source-disable")
    def disable_tool_source(
        ctx: typer.Context,
        source_id: str = typer.Argument(..., help="Tool source identifier."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            container.require(
                AppKey.TOOL_SOURCE_COMMAND_SERVICE,
            ).disable_source(source_id),
        )

    @app.command("source-restore")
    def restore_tool_source(
        ctx: typer.Context,
        source_id: str = typer.Argument(..., help="Tool source identifier."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            container.require(
                AppKey.TOOL_SOURCE_COMMAND_SERVICE,
            ).restore_source(source_id),
        )

    @app.command("source-delete")
    def delete_tool_source(
        ctx: typer.Context,
        source_id: str = typer.Argument(..., help="Tool source identifier."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            container.require(
                AppKey.TOOL_SOURCE_COMMAND_SERVICE,
            ).delete_source(source_id),
        )

    @app.command("functions")
    def list_tool_functions(
        ctx: typer.Context,
        source_id: str | None = typer.Option(None, "--source-id"),
        status: str | None = typer.Option(None, "--status"),
    ) -> None:
        container = ensure_container(ctx)
        functions = container.require(AppKey.TOOL_SOURCE_QUERY_SERVICE).list_functions(
            source_id=source_id,
            status=status,
        )
        echo_data(functions)

    @app.command("function-enable")
    def enable_tool_function(
        ctx: typer.Context,
        function_id: str = typer.Argument(..., help="Tool function identifier."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            container.require(
                AppKey.TOOL_FUNCTION_COMMAND_SERVICE,
            ).set_function_enabled(function_id, enabled=True),
        )

    @app.command("function-disable")
    def disable_tool_function(
        ctx: typer.Context,
        function_id: str = typer.Argument(..., help="Tool function identifier."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            container.require(
                AppKey.TOOL_FUNCTION_COMMAND_SERVICE,
            ).set_function_enabled(function_id, enabled=False),
        )

    @app.command("function-policy")
    def update_tool_function_policy(
        ctx: typer.Context,
        function_id: str = typer.Argument(..., help="Tool function identifier."),
        trust_policy: str = typer.Option(
            "{}",
            "--trust-policy",
            help="JSON object stored as ToolFunction trust policy.",
        ),
        approval_policy: str = typer.Option(
            "{}",
            "--approval-policy",
            help="JSON object stored as ToolFunction approval policy.",
        ),
        credential_binding_overrides: str = typer.Option(
            "{}",
            "--credential-binding-overrides",
            help="JSON object mapping credential slot to Access binding id.",
        ),
        required_effect_overrides: str | None = typer.Option(
            None,
            "--required-effect-overrides",
            help="Comma-separated effect ids, or omit to clear overrides.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        binding_overrides = _parse_json_object(credential_binding_overrides)
        echo_data(
            container.require(
                AppKey.TOOL_FUNCTION_COMMAND_SERVICE,
            ).update_function_policy(
                function_id,
                trust_policy=_parse_json_object(trust_policy),
                approval_policy=_parse_json_object(approval_policy),
                credential_binding_overrides={
                    str(key): str(value)
                    for key, value in binding_overrides.items()
                },
                required_effect_overrides=(
                    _parse_text_tuple(required_effect_overrides)
                    if required_effect_overrides is not None
                    else None
                ),
            ),
        )

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
        arguments = _parse_json_object(input_payload)
        authorize_tool_run(
            container,
            tool_id=tool_id,
            mode=mode,
            strategy=strategy,
            environment=environment,
            interface_name="cli",
            arguments=arguments,
        )
        tool_run = asyncio.run(
            container.require(AppKey.TOOL_SERVICE).execute(
                ExecuteToolInput(
                    tool_id=tool_id,
                    arguments=arguments,
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
        limit: int = typer.Option(
            100,
            "--limit",
            min=1,
            help="Maximum number of latest runs to list.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        runs = container.require(AppKey.TOOL_SERVICE).list_tool_runs(
            tool_id=tool_id,
            limit=limit,
        )
        echo_data([ToolRunDTO.from_entity(run) for run in runs])

    @app.command("get-run")
    def get_tool_run(
        ctx: typer.Context,
        run_id: str = typer.Argument(..., help="Tool run identifier."),
    ) -> None:
        container = ensure_container(ctx)
        tool_run = container.require(AppKey.TOOL_SERVICE).get_tool_run(run_id)
        echo_data(ToolRunDTO.from_entity(tool_run))

    @app.command("cancel-run")
    def cancel_tool_run(
        ctx: typer.Context,
        run_id: str = typer.Argument(..., help="Tool run identifier."),
    ) -> None:
        container = ensure_container(ctx)
        tool_run = container.require(AppKey.TOOL_SERVICE).cancel_tool_run(run_id)
        echo_data(ToolRunDTO.from_entity(tool_run))

    return app


def _source_sync_payload(result) -> dict[str, object]:  # noqa: ANN001
    discovery = None
    if result.discovery is not None:
        discovery = {
            "source_id": result.discovery.source_id,
            "status": result.discovery.status.value,
            "discovered_at": result.discovery.discovered_at,
            "function_count": len(result.discovery.candidates),
            "provider_backend_count": len(
                result.discovery.provider_backend_candidates,
            ),
            "error_message": result.discovery.error_message,
            "metadata": dict(result.discovery.metadata),
        }
    return {
        "source": result.source,
        "skipped": result.skipped,
        "error_message": result.error_message,
        "discovery": discovery,
        "changed": result.changed,
    }
