from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
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
        context = container.require(AppKey.MEMORY_CONTEXT_RESOLVER).resolve(agent_id)
        if context is None:
            _exit_not_found("No file-backed memory context is available for this agent.")
        long_term = container.require(AppKey.FILE_MEMORY_SERVICE).get(
            context=context,
            path="MEMORY.md",
        )
        if long_term is None:
            long_term = container.require(AppKey.FILE_MEMORY_SERVICE).get(
                context=context,
                path="memory.md",
            )
        recent_files = container.require(AppKey.FILE_MEMORY_SERVICE).list_files(
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

    @app.command("spaces")
    def spaces(
        ctx: typer.Context,
        include_disabled: bool = typer.Option(False, help="Include disabled spaces."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            container.require(AppKey.MEMORY_SPACE_SERVICE).list_spaces(
                include_disabled=include_disabled,
            ),
        )

    @app.command("migrate-legacy-agent-homes")
    def migrate_legacy_agent_homes(
        ctx: typer.Context,
        agent_id: list[str] = typer.Option(
            (),
            "--agent-id",
            help="Limit migration to a specific agent id. Repeat to migrate several.",
        ),
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="Report planned profile/space/file changes without writing.",
        ),
        delete_sidecar: bool = typer.Option(
            False,
            "--delete-sidecar",
            help="Delete imported .state/memory-binding.json files after migration.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        report = container.require(
            AppKey.MEMORY_LEGACY_MIGRATION_SERVICE,
        ).migrate_agent_homes(
            agent_ids=tuple(agent_id),
            dry_run=dry_run,
            delete_sidecar=delete_sidecar,
        )
        echo_data(
            {
                "dry_run": report.dry_run,
                "scanned": report.scanned,
                "updated_profiles": report.updated_profiles,
                "created_spaces": report.created_spaces,
                "copied_files": report.copied_files,
                "agents": report.agents,
            },
        )

    @app.command("policies")
    def policies(
        ctx: typer.Context,
        include_disabled: bool = typer.Option(False, help="Include disabled policies."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            container.require(AppKey.MEMORY_POLICY_SERVICE).list_policies(
                include_disabled=include_disabled,
            ),
        )

    @app.command("policy-set")
    def policy_set(
        ctx: typer.Context,
        policy_id: str = typer.Argument(..., help="Memory policy identifier."),
        target_kind: str = typer.Option(
            ...,
            help="Policy target kind: global, space, or agent.",
        ),
        target_id: str | None = typer.Option(
            None,
            help="Target scope or agent id. Omit for global policies.",
        ),
        recall_enabled: bool = typer.Option(True, help="Allow memory recall."),
        remember_enabled: bool = typer.Option(True, help="Allow memory writes."),
        max_recall_items: int = typer.Option(6, min=1, max=100, help="Recall item cap."),
        retention: str = typer.Option("engine_default", help="Default retention hint."),
        status: str = typer.Option("active", help="Policy status: active or disabled."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(
            container.require(AppKey.MEMORY_POLICY_SERVICE).upsert_policy(
                policy_id=policy_id,
                target_kind=target_kind,
                target_id=target_id,
                recall_enabled=recall_enabled,
                remember_enabled=remember_enabled,
                max_recall_items=max_recall_items,
                retention=retention,
                status=status,
            ),
        )

    @app.command("policy-disable")
    def policy_disable(
        ctx: typer.Context,
        policy_id: str = typer.Argument(..., help="Memory policy identifier."),
    ) -> None:
        container = ensure_container(ctx)
        policy = container.require(AppKey.MEMORY_POLICY_SERVICE).disable_policy(policy_id)
        if policy is None:
            _exit_not_found("Memory policy was not found.")
        echo_data(policy)

    @app.command("policy-delete")
    def policy_delete(
        ctx: typer.Context,
        policy_id: str = typer.Argument(..., help="Memory policy identifier."),
    ) -> None:
        container = ensure_container(ctx)
        container.require(AppKey.MEMORY_POLICY_SERVICE).delete_policy(policy_id)
        echo_data({"deleted": policy_id})

    @app.command("search")
    def search(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent identifier."),
        query: str = typer.Argument(..., help="Search query."),
        limit: int = typer.Option(12, min=1, max=50, help="Maximum number of hits."),
    ) -> None:
        container = ensure_container(ctx)
        context = container.require(AppKey.MEMORY_CONTEXT_RESOLVER).resolve(agent_id)
        if context is None:
            _exit_not_found("No file-backed memory context is available for this agent.")
        echo_data(
            container.require(AppKey.FILE_MEMORY_SERVICE).search(
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
        context = container.require(AppKey.MEMORY_CONTEXT_RESOLVER).resolve(agent_id)
        if context is None:
            _exit_not_found("No file-backed memory context is available for this agent.")
        result = container.require(AppKey.FILE_MEMORY_SERVICE).get(
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
        context = container.require(AppKey.MEMORY_CONTEXT_RESOLVER).resolve(agent_id)
        if context is None:
            _exit_not_found("No file-backed memory context is available for this agent.")
        echo_data(
            container.require(AppKey.FILE_MEMORY_SERVICE).append_daily(
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
        context = container.require(AppKey.MEMORY_CONTEXT_RESOLVER).resolve(agent_id)
        if context is None:
            _exit_not_found("No file-backed memory context is available for this agent.")
        echo_data(
            container.require(AppKey.FILE_MEMORY_SERVICE).write_long_term(
                context=context,
                content=content,
            ),
        )

    return app
