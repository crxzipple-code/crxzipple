from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    EnsureContextWorkspaceInput,
    ContextObservationRenderInput,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextActor,
    ContextActorKind,
    ContextActionNotAllowedError,
    ContextNodeNotFoundError,
    ContextWorkspaceNotFoundError,
)
from crxzipple.modules.context_workspace.interfaces.http import (
    _node_payload,
    _tree_payload,
    _workspace_payload,
)


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Inspect and control context workspaces.", no_args_is_help=True)

    @app.command("ensure")
    def ensure(
        ctx: typer.Context,
        session_key: str = typer.Argument(..., help="Stable session key."),
        agent_id: str = typer.Option(..., help="Agent identifier."),
    ) -> None:
        container = ensure_container(ctx)
        workspace = container.require(AppKey.CONTEXT_WORKSPACE_SERVICE).ensure_workspace(
            EnsureContextWorkspaceInput(session_key=session_key, agent_id=agent_id),
        )
        echo_data(_workspace_payload(workspace))

    @app.command("tree")
    def tree(
        ctx: typer.Context,
        session_key: str = typer.Argument(..., help="Stable session key."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            view = container.require(AppKey.CONTEXT_TREE_SERVICE).list_tree(session_key)
        except ContextWorkspaceNotFoundError as exc:
            _exit_not_found(exc)
        echo_data(_tree_payload(view.workspace, view.nodes, view.estimate))

    @app.command("estimate")
    def estimate(
        ctx: typer.Context,
        session_key: str = typer.Argument(..., help="Stable session key."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            view = container.require(AppKey.CONTEXT_TREE_SERVICE).list_tree(session_key)
        except ContextWorkspaceNotFoundError as exc:
            _exit_not_found(exc)
        echo_data(
            {
                "workspace": _workspace_payload(view.workspace),
                "estimate": view.estimate.to_payload(),
            },
        )

    @app.command("render")
    def render(
        ctx: typer.Context,
        session_key: str = typer.Argument(..., help="Stable session key."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.CONTEXT_OBSERVATION_SNAPSHOT_SERVICE).render_observation(
                ContextObservationRenderInput(session_key=session_key),
            )
        except ContextWorkspaceNotFoundError as exc:
            _exit_not_found(exc)
        echo_data(
            {
                "workspace": _workspace_payload(result.workspace),
                "debug_body": result.debug_body,
                "estimate": result.estimate.to_payload(),
                "included_node_ids": list(result.included_node_ids),
            },
        )

    @app.command("action")
    def action(
        ctx: typer.Context,
        session_key: str = typer.Argument(..., help="Stable session key."),
        node_id: str = typer.Argument(..., help="Context node id."),
        action_name: ContextAction = typer.Argument(..., help="Action name."),
        actor_id: str | None = typer.Option(None, help="Optional actor id."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            result = container.require(AppKey.CONTEXT_TREE_SERVICE).apply_action(
                ContextActionInput(
                    session_key=session_key,
                    node_id=node_id,
                    action=action_name,
                    actor=ContextActor(
                        kind=ContextActorKind.USER,
                        actor_id=actor_id,
                    ),
                ),
            )
        except (ContextWorkspaceNotFoundError, ContextNodeNotFoundError) as exc:
            _exit_not_found(exc)
        except ContextActionNotAllowedError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=2) from None
        echo_data(
            {
                "workspace": _workspace_payload(result.workspace),
                "node": _node_payload(result.node),
                "action": result.action.value,
                "operation_id": result.operation_id,
            },
        )

    return app


def _exit_not_found(exc: Exception) -> None:
    typer.secho(str(exc), err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1) from None


__all__ = ["build_cli"]
