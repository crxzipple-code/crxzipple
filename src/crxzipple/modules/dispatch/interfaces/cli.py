from __future__ import annotations

import json

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.dispatch.application import (
    CancelDispatchTaskInput,
    CompleteDispatchTaskInput,
    CreateDispatchTaskInput,
    EnqueueDispatchTaskInput,
    FailDispatchTaskInput,
    HeartbeatDispatchTaskInput,
    RequeueDispatchTaskInput,
    RecoverAbandonedDispatchTasksInput,
    WaitDispatchTaskInput,
)
from crxzipple.modules.dispatch.domain import (
    DispatchPolicy,
    DispatchTaskNotFoundError,
    DispatchTaskStatus,
    DispatchValidationError,
)
from crxzipple.modules.dispatch.interfaces.dto import DispatchTaskDTO


def _parse_json_object(raw: str | None, *, option_name: str) -> dict[str, object]:
    if raw is None or not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(
            f"{option_name} must be valid JSON: {exc.msg}",
        ) from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter(f"{option_name} must decode to a JSON object.")
    return dict(payload)


def _parse_policy(raw: str | None) -> DispatchPolicy | None:
    if raw is None:
        return None
    try:
        return DispatchPolicy(raw)
    except ValueError as exc:
        values = ", ".join(item.value for item in DispatchPolicy)
        raise typer.BadParameter(
            f"--policy must be one of: {values}",
        ) from exc


def _parse_status(raw: str | None) -> DispatchTaskStatus | None:
    if raw is None:
        return None
    try:
        return DispatchTaskStatus(raw)
    except ValueError as exc:
        values = ", ".join(item.value for item in DispatchTaskStatus)
        raise typer.BadParameter(
            f"--status must be one of: {values}",
        ) from exc


def _exit_not_found(exc: DispatchTaskNotFoundError) -> None:
    typer.secho(str(exc), err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1) from None


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage dispatch tasks.", no_args_is_help=True)

    @app.command("create")
    def create_task(
        ctx: typer.Context,
        owner_kind: str = typer.Argument(..., help="Owning subsystem kind."),
        owner_id: str = typer.Argument(..., help="Owner identifier."),
        task_id: str | None = typer.Option(None, help="Optional dispatch task id."),
        lane_key: str | None = typer.Option(None, help="Optional lane key."),
        policy: str = typer.Option(
            DispatchPolicy.FIFO.value,
            help="Dispatch ordering policy.",
        ),
        priority: int = typer.Option(100, min=0, help="Dispatch priority."),
        payload_ref: str | None = typer.Option(
            None,
            help="Opaque payload reference.",
        ),
        metadata: str | None = typer.Option(
            None,
            help="Optional metadata JSON object.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            task = container.require(AppKey.DISPATCH_SERVICE).create_task(
                CreateDispatchTaskInput(
                    task_id=task_id,
                    owner_kind=owner_kind,
                    owner_id=owner_id,
                    lane_key=lane_key,
                    policy=_parse_policy(policy) or DispatchPolicy.FIFO,
                    priority=priority,
                    payload_ref=payload_ref,
                    metadata=_parse_json_object(metadata, option_name="--metadata"),
                ),
            )
        except DispatchValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data(DispatchTaskDTO.from_entity(task))

    @app.command("get")
    def get_task(
        ctx: typer.Context,
        task_id: str = typer.Argument(..., help="Dispatch task identifier."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            task = container.require(AppKey.DISPATCH_SERVICE).get_task(task_id)
        except DispatchTaskNotFoundError as exc:
            _exit_not_found(exc)
        echo_data(DispatchTaskDTO.from_entity(task))

    @app.command("list")
    def list_tasks(
        ctx: typer.Context,
        status: str | None = typer.Option(None, help="Optional status filter."),
        owner_kind: str | None = typer.Option(None, help="Optional owner kind filter."),
        lane_key: str | None = typer.Option(None, help="Optional lane key filter."),
    ) -> None:
        container = ensure_container(ctx)
        tasks = container.require(AppKey.DISPATCH_SERVICE).list_tasks(
            status=_parse_status(status),
            owner_kind=owner_kind,
            lane_key=lane_key,
        )
        echo_data([DispatchTaskDTO.from_entity(task) for task in tasks])

    @app.command("enqueue")
    def enqueue_task(
        ctx: typer.Context,
        task_id: str = typer.Argument(..., help="Dispatch task identifier."),
        lane_key: str | None = typer.Option(None, help="Optional replacement lane key."),
        policy: str | None = typer.Option(None, help="Optional replacement policy."),
        priority: int | None = typer.Option(None, min=0, help="Optional replacement priority."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            task = container.require(AppKey.DISPATCH_SERVICE).enqueue_task(
                EnqueueDispatchTaskInput(
                    task_id=task_id,
                    lane_key=lane_key,
                    policy=_parse_policy(policy),
                    priority=priority,
                ),
            )
        except DispatchTaskNotFoundError as exc:
            _exit_not_found(exc)
        except DispatchValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data(DispatchTaskDTO.from_entity(task))

    @app.command("claim-next")
    def claim_next(
        ctx: typer.Context,
        owner_kind: str | None = typer.Option(None, help="Optional owner kind filter."),
        worker_id: str = typer.Option(..., help="Worker identifier."),
        claim_token: str | None = typer.Option(None, help="Optional claim token."),
        lease_seconds: int | None = typer.Option(
            None,
            min=1,
            help="Optional lease duration in seconds.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            task = container.require(AppKey.DISPATCH_SERVICE).claim_next_queued_task(
                owner_kind=owner_kind,
                worker_id=worker_id,
                claim_token=claim_token,
                lease_seconds=lease_seconds,
            )
        except DispatchValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data(None if task is None else DispatchTaskDTO.from_entity(task))

    @app.command("wait")
    def wait_task(
        ctx: typer.Context,
        task_id: str = typer.Argument(..., help="Dispatch task identifier."),
        reason: str | None = typer.Option(None, help="Optional waiting reason."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            task = container.require(AppKey.DISPATCH_SERVICE).wait_task(
                WaitDispatchTaskInput(task_id=task_id, reason=reason),
            )
        except DispatchTaskNotFoundError as exc:
            _exit_not_found(exc)
        except DispatchValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data(DispatchTaskDTO.from_entity(task))

    @app.command("heartbeat")
    def heartbeat_task(
        ctx: typer.Context,
        task_id: str = typer.Argument(..., help="Dispatch task identifier."),
        worker_id: str = typer.Option(..., help="Worker identifier."),
        lease_seconds: int = typer.Option(..., min=1, help="Lease duration in seconds."),
        claim_token: str | None = typer.Option(None, help="Optional claim token."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            task = container.require(AppKey.DISPATCH_SERVICE).heartbeat_task(
                HeartbeatDispatchTaskInput(
                    task_id=task_id,
                    worker_id=worker_id,
                    lease_seconds=lease_seconds,
                    claim_token=claim_token,
                ),
            )
        except DispatchTaskNotFoundError as exc:
            _exit_not_found(exc)
        except DispatchValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data(DispatchTaskDTO.from_entity(task))

    @app.command("requeue")
    def requeue_task(
        ctx: typer.Context,
        task_id: str = typer.Argument(..., help="Dispatch task identifier."),
        policy: str | None = typer.Option(None, help="Optional replacement policy."),
        priority: int | None = typer.Option(None, min=0, help="Optional replacement priority."),
        reason: str | None = typer.Option(None, help="Optional requeue reason."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            task = container.require(AppKey.DISPATCH_SERVICE).requeue_task(
                RequeueDispatchTaskInput(
                    task_id=task_id,
                    policy=_parse_policy(policy),
                    priority=priority,
                    reason=reason,
                ),
            )
        except DispatchTaskNotFoundError as exc:
            _exit_not_found(exc)
        except DispatchValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data(DispatchTaskDTO.from_entity(task))

    @app.command("recover-abandoned")
    def recover_abandoned_tasks(
        ctx: typer.Context,
        owner_kind: str | None = typer.Option(None, help="Optional owner kind filter."),
        reason: str = typer.Option(
            "Dispatch worker lease expired before completion.",
            help="Reason recorded on recovered tasks.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            tasks = container.require(AppKey.DISPATCH_SERVICE).recover_abandoned_tasks(
                RecoverAbandonedDispatchTasksInput(
                    owner_kind=owner_kind,
                    reason=reason,
                ),
            )
        except DispatchValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data([DispatchTaskDTO.from_entity(task) for task in tasks])

    @app.command("complete")
    def complete_task(
        ctx: typer.Context,
        task_id: str = typer.Argument(..., help="Dispatch task identifier."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            task = container.require(AppKey.DISPATCH_SERVICE).complete_task(
                CompleteDispatchTaskInput(task_id=task_id),
            )
        except DispatchTaskNotFoundError as exc:
            _exit_not_found(exc)
        except DispatchValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data(DispatchTaskDTO.from_entity(task))

    @app.command("cancel")
    def cancel_task(
        ctx: typer.Context,
        task_id: str = typer.Argument(..., help="Dispatch task identifier."),
        reason: str | None = typer.Option(None, help="Optional cancellation reason."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            task = container.require(AppKey.DISPATCH_SERVICE).cancel_task(
                CancelDispatchTaskInput(task_id=task_id, reason=reason),
            )
        except DispatchTaskNotFoundError as exc:
            _exit_not_found(exc)
        except DispatchValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data(DispatchTaskDTO.from_entity(task))

    @app.command("fail")
    def fail_task(
        ctx: typer.Context,
        task_id: str = typer.Argument(..., help="Dispatch task identifier."),
        message: str = typer.Option(..., help="Failure message."),
        code: str = typer.Option("dispatch_failed", help="Failure code."),
        details: str | None = typer.Option(
            None,
            help="Optional failure details JSON object.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            task = container.require(AppKey.DISPATCH_SERVICE).fail_task(
                FailDispatchTaskInput(
                    task_id=task_id,
                    message=message,
                    code=code,
                    details=_parse_json_object(details, option_name="--details"),
                ),
            )
        except DispatchTaskNotFoundError as exc:
            _exit_not_found(exc)
        except DispatchValidationError as exc:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from None
        echo_data(DispatchTaskDTO.from_entity(task))

    return app
