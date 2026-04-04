from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data


def _exit_not_found(message: str) -> None:
    typer.secho(message, err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1) from None


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage file-backed memory.", no_args_is_help=True)

    @app.command("overview")
    def overview(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent identifier."),
        recent_limit: int = typer.Option(12, min=1, max=50, help="Maximum recent files."),
    ) -> None:
        container = ensure_container(ctx)
        context = container.memory_context_resolver.resolve(agent_id)
        if context is None:
            _exit_not_found("No file-backed memory context is available for this agent.")
        long_term = container.file_memory_service.get(
            context=context,
            path="MEMORY.md",
        )
        if long_term is None:
            long_term = container.file_memory_service.get(
                context=context,
                path="memory.md",
            )
        recent_files = container.file_memory_service.list_files(
            context=context,
            limit=recent_limit,
        )
        echo_data(
            {
                "agent_id": agent_id,
                "space_id": context.space_id,
                "long_term": long_term,
                "recent_files": recent_files,
            },
        )

    @app.command("search")
    def search(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent identifier."),
        query: str = typer.Argument(..., help="Search query."),
        limit: int = typer.Option(12, min=1, max=50, help="Maximum number of hits."),
    ) -> None:
        container = ensure_container(ctx)
        context = container.memory_context_resolver.resolve(agent_id)
        if context is None:
            _exit_not_found("No file-backed memory context is available for this agent.")
        echo_data(
            container.file_memory_service.search(
                context=context,
                query=query,
                limit=limit,
            ),
        )

    @app.command("excerpt")
    def excerpt(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent identifier."),
        path: str = typer.Argument(..., help="Relative memory file path."),
        start_line: int | None = typer.Option(None, min=1, help="Optional 1-based start line."),
        line_count: int | None = typer.Option(
            None,
            min=1,
            max=500,
            help="Optional number of lines to read.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        context = container.memory_context_resolver.resolve(agent_id)
        if context is None:
            _exit_not_found("No file-backed memory context is available for this agent.")
        result = container.file_memory_service.get(
            context=context,
            path=path,
            start_line=start_line,
            line_count=line_count,
        )
        if result is None:
            _exit_not_found("Memory excerpt was not found.")
        echo_data(result)

    @app.command("write-daily")
    def write_daily(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent identifier."),
        content: str = typer.Argument(..., help="Daily memory content."),
        title: str | None = typer.Option(None, help="Optional section title."),
    ) -> None:
        container = ensure_container(ctx)
        context = container.memory_context_resolver.resolve(agent_id)
        if context is None:
            _exit_not_found("No file-backed memory context is available for this agent.")
        echo_data(
            container.file_memory_service.append_daily(
                context=context,
                content=content,
                title=title,
            ),
        )

    @app.command("write-long-term")
    def write_long_term(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent identifier."),
        content: str = typer.Argument(..., help="Long-term memory content."),
    ) -> None:
        container = ensure_container(ctx)
        context = container.memory_context_resolver.resolve(agent_id)
        if context is None:
            _exit_not_found("No file-backed memory context is available for this agent.")
        echo_data(
            container.file_memory_service.write_long_term(
                context=context,
                content=content,
            ),
        )

    return app
