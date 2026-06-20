from __future__ import annotations

import typer

from crxzipple.interfaces.cli.context import AppKey, ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.session.application import (
    AppendSessionItemInput,
    ListSessionItemsInput,
    ListSessionInstancesInput,
    ResetSessionInput,
    SessionResolutionService,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionItemKind,
    SessionItemPhase,
    SessionInstanceNotFoundError,
    SessionNotFoundError,
)
from crxzipple.modules.session.interfaces.dto import (
    ResolveSessionDTO,
    SessionDTO,
    SessionItemDTO,
    SessionInstanceDTO,
)
from crxzipple.modules.session.interfaces.shared import (
    build_ensure_session_input,
    build_reset_policy,
    build_resolve_session_input,
    parse_json_object,
)


def _bad_parameter(message: str) -> typer.BadParameter:
    return typer.BadParameter(message)


def _exit_not_found(
    exc: SessionNotFoundError | SessionInstanceNotFoundError,
) -> None:
    typer.secho(str(exc), err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1) from None


def _parse_direct_scope(raw: str) -> DirectSessionScope:
    try:
        return DirectSessionScope(raw)
    except ValueError as exc:
        values = ", ".join(scope.value for scope in DirectSessionScope)
        raise typer.BadParameter(
            f"--direct-scope must be one of: {values}",
        ) from exc


def _parse_json_option(raw: str | None, *, option_name: str) -> dict[str, object]:
    return parse_json_object(
        raw,
        option_name=option_name,
        error_factory=_bad_parameter,
    )


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage sessions.", no_args_is_help=True)

    @app.command("start")
    def start_session(
        ctx: typer.Context,
        session_key: str = typer.Argument(..., help="Stable session key."),
        agent_id: str | None = typer.Option(None, help="Runtime binding agent identifier."),
        status: str = typer.Option("active", help="Session status."),
        channel: str | None = typer.Option(None, help="Optional channel identifier."),
        chat_type: str | None = typer.Option(None, help="Optional chat type."),
        origin: str | None = typer.Option(
            None,
            help="Optional origin JSON object.",
        ),
        reply: str | None = typer.Option(
            None,
            help="Optional reply JSON object.",
        ),
        metadata: str | None = typer.Option(
            None,
            help="Optional metadata JSON object.",
        ),
        runtime_binding: str | None = typer.Option(
            None,
            help="Optional runtime binding JSON object.",
        ),
        active_session_id: str | None = typer.Option(
            None,
            help="Optional active session instance id.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        session = container.require(AppKey.SESSION_SERVICE).ensure_session(
            build_ensure_session_input(
                key=session_key,
                runtime_binding_payload=_parse_json_option(
                runtime_binding,
                option_name="--runtime-binding",
            ),
            agent_id=agent_id,
            status=status,
                channel=channel,
                chat_type=chat_type,
                origin_payload=(
                    _parse_json_option(origin, option_name="--origin")
                    if origin is not None
                    else None
                ),
                reply_payload=(
                    _parse_json_option(reply, option_name="--reply")
                    if reply is not None
                    else None
                ),
                metadata=_parse_json_option(metadata, option_name="--metadata"),
                active_session_id=active_session_id,
                error_factory=_bad_parameter,
            ),
        )
        echo_data(SessionDTO.from_entity(session))

    @app.command("get")
    def get_session(
        ctx: typer.Context,
        session_key: str = typer.Argument(..., help="Stable session key."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            session = container.require(AppKey.SESSION_SERVICE).get_session(session_key)
        except SessionNotFoundError as exc:
            _exit_not_found(exc)
        echo_data(SessionDTO.from_entity(session))

    @app.command("list")
    def list_sessions(
        ctx: typer.Context,
        agent_id: str | None = typer.Option(None, help="Optional agent id filter."),
    ) -> None:
        container = ensure_container(ctx)
        items = [
            SessionDTO.from_entity(session)
            for session in container.require(AppKey.SESSION_SERVICE).list_sessions(agent_id=agent_id)
        ]
        echo_data(items)

    @app.command("resolve-key")
    def resolve_key(
        ctx: typer.Context,
        agent_id: str = typer.Argument(..., help="Agent identifier."),
        channel: str | None = typer.Option(None, help="Optional channel identifier."),
        chat_type: str = typer.Option("direct", help="Chat type for routing."),
        peer_id: str | None = typer.Option(None, help="Optional peer identifier."),
        conversation_id: str | None = typer.Option(
            None,
            help="Optional group or channel conversation identifier.",
        ),
        thread_id: str | None = typer.Option(None, help="Optional thread identifier."),
        account_id: str | None = typer.Option(None, help="Optional account identifier."),
        label: str | None = typer.Option(None, help="Optional origin label."),
        surface: str | None = typer.Option(None, help="Optional origin surface."),
        main_key: str = typer.Option("main", help="Stable main-session suffix."),
        direct_scope: str = typer.Option(
            DirectSessionScope.MAIN.value,
            help="Direct message routing scope.",
        ),
        status: str = typer.Option("active", help="Session status."),
        metadata: str | None = typer.Option(
            None,
            help="Optional metadata JSON object.",
        ),
        ensure: bool = typer.Option(
            False,
            "--ensure/--no-ensure",
            help="Create or update the session if it does not exist.",
        ),
        touch_activity: bool = typer.Option(
            True,
            "--touch-activity/--no-touch-activity",
            help="Refresh session activity timestamps while ensuring.",
        ),
        idle_minutes: int | None = typer.Option(
            None,
            min=1,
            help="Reset the active instance after this many idle minutes.",
        ),
        daily_reset_hour_utc: int | None = typer.Option(
            None,
            min=0,
            max=23,
            help="Reset the active instance at this UTC hour each day.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        resolution_service: SessionResolutionService = (
            container.require(AppKey.SESSION_RESOLUTION_SERVICE)
        )
        bundle = resolution_service.resolve(
            build_resolve_session_input(
                agent_id=agent_id,
                channel=channel,
                chat_type=chat_type,
                peer_id=peer_id,
                conversation_id=conversation_id,
                thread_id=thread_id,
                account_id=account_id,
                label=label,
                surface=surface,
                main_key=main_key,
                direct_scope=_parse_direct_scope(direct_scope),
                status=status,
                metadata=_parse_json_option(metadata, option_name="--metadata"),
                ensure=ensure,
                touch_activity=touch_activity,
                reset_policy=build_reset_policy(
                    idle_minutes=idle_minutes,
                    daily_reset_hour_utc=daily_reset_hour_utc,
                ),
            ),
        )
        echo_data(ResolveSessionDTO.from_result(bundle.resolution))

    @app.command("append-item")
    def append_item(
        ctx: typer.Context,
        session_key: str = typer.Argument(..., help="Stable session key."),
        kind: SessionItemKind = typer.Argument(..., help="Session item kind."),
        role: str | None = typer.Option(None, help="Optional provider role."),
        phase: SessionItemPhase = typer.Option(
            SessionItemPhase.UNKNOWN,
            help="Session item phase.",
        ),
        content_payload: str | None = typer.Option(
            None,
            help="Optional structured content JSON object.",
        ),
        source_module: str | None = typer.Option(
            None,
            help="Optional provenance source module.",
        ),
        source_kind: str | None = typer.Option(
            None,
            help="Optional provenance source kind.",
        ),
        source_id: str | None = typer.Option(
            None,
            help="Optional provenance source id.",
        ),
        provider_item_id: str | None = typer.Option(
            None,
            help="Optional provider-native item id.",
        ),
        provider_item_type: str | None = typer.Option(
            None,
            help="Optional provider-native item type.",
        ),
        call_id: str | None = typer.Option(None, help="Optional tool call id."),
        tool_name: str | None = typer.Option(None, help="Optional tool name."),
        metadata: str | None = typer.Option(
            None,
            help="Optional item metadata JSON object.",
        ),
        session_id: str | None = typer.Option(
            None,
            help="Optional session instance id override.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            item = container.require(AppKey.SESSION_SERVICE).append_item(
                AppendSessionItemInput(
                    session_key=session_key,
                    kind=kind,
                    role=role,
                    phase=phase,
                    content_payload=_parse_json_option(
                        content_payload,
                        option_name="--content-payload",
                    ),
                    source_module=source_module,
                    source_kind=source_kind,
                    source_id=source_id,
                    provider_item_id=provider_item_id,
                    provider_item_type=provider_item_type,
                    call_id=call_id,
                    tool_name=tool_name,
                    metadata=_parse_json_option(metadata, option_name="--metadata"),
                    session_id=session_id,
                ),
            )
        except (SessionNotFoundError, SessionInstanceNotFoundError) as exc:
            _exit_not_found(exc)
        echo_data(SessionItemDTO.from_entity(item))

    @app.command("items")
    def items(
        ctx: typer.Context,
        session_key: str = typer.Argument(..., help="Stable session key."),
        limit: int | None = typer.Option(None, min=1, help="Optional item limit."),
        active_only: bool = typer.Option(
            False,
            "--active-only/--all",
            help="Only show items for the active session instance.",
        ),
        before_sequence_no: int | None = typer.Option(
            None,
            min=1,
            help="Optional upper sequence bound for loading older items.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            item_list = container.require(AppKey.SESSION_SERVICE).list_items(
                ListSessionItemsInput(
                    session_key=session_key,
                    limit=limit,
                    active_session_only=active_only,
                    before_sequence_no=before_sequence_no,
                ),
            )
        except SessionNotFoundError as exc:
            _exit_not_found(exc)
        echo_data([SessionItemDTO.from_entity(item) for item in item_list])

    @app.command("instances")
    def list_instances(
        ctx: typer.Context,
        session_key: str = typer.Argument(..., help="Stable session key."),
    ) -> None:
        container = ensure_container(ctx)
        try:
            items = container.require(AppKey.SESSION_SERVICE).list_instances(
                ListSessionInstancesInput(session_key=session_key),
            )
        except SessionNotFoundError as exc:
            _exit_not_found(exc)
        echo_data([SessionInstanceDTO.from_entity(item) for item in items])

    @app.command("reset")
    def reset_session(
        ctx: typer.Context,
        session_key: str = typer.Argument(..., help="Stable session key."),
        status: str | None = typer.Option(None, help="Optional replacement status."),
        metadata: str | None = typer.Option(
            None,
            help="Optional metadata JSON object merged into the session.",
        ),
        active_session_id: str | None = typer.Option(
            None,
            help="Optional explicit active session instance id.",
        ),
        reason: str | None = typer.Option(
            None,
            help="Optional reset reason.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        try:
            session = container.require(AppKey.SESSION_SERVICE).reset_session(
                ResetSessionInput(
                    session_key=session_key,
                    status=status,
                    metadata=_parse_json_option(metadata, option_name="--metadata"),
                    active_session_id=active_session_id,
                    reason=reason,
                ),
            )
        except SessionNotFoundError as exc:
            _exit_not_found(exc)
        echo_data(SessionDTO.from_entity(session))

    return app
