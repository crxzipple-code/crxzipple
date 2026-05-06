from __future__ import annotations

import json

import typer

from crxzipple.core.config import LlmProfileSettings
from crxzipple.interfaces.authorization import authorize_llm_action
from crxzipple.interfaces.cli.context import ensure_container
from crxzipple.interfaces.cli.formatters import echo_data
from crxzipple.modules.llm.application import InvokeLlmInput, RegisterLlmProfileInput
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmDefaults,
    LlmMessage,
    LlmMessageRole,
    LlmModelFamily,
    LlmProviderKind,
    LlmSourceKind,
    ToolSchema,
)
from crxzipple.modules.llm.interfaces.dto import LlmInvocationDTO, LlmProfileDTO


def _load_json(value: str | None, option_name: str) -> object:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(
            f"{option_name} must be valid JSON: {exc.msg}",
        ) from exc


def _parse_messages(raw: str) -> tuple[LlmMessage, ...]:
    payload = _load_json(raw, "--messages")
    if not isinstance(payload, list):
        raise typer.BadParameter("--messages must be a JSON array.")
    messages: list[LlmMessage] = []
    for item in payload:
        if not isinstance(item, dict):
            raise typer.BadParameter("--messages items must be JSON objects.")
        messages.append(
            LlmMessage(
                role=LlmMessageRole(item["role"]),
                content=item.get("content"),
                name=item.get("name"),
                tool_call_id=item.get("tool_call_id"),
                metadata=(
                    dict(item.get("metadata"))
                    if isinstance(item.get("metadata"), dict)
                    else {}
                ),
            ),
        )
    return tuple(messages)


def _parse_tool_schemas(raw: str | None) -> tuple[ToolSchema, ...]:
    payload = _load_json(raw, "--tool-schemas")
    if payload is None:
        return ()
    if not isinstance(payload, list):
        raise typer.BadParameter("--tool-schemas must be a JSON array.")
    schemas: list[ToolSchema] = []
    for item in payload:
        if not isinstance(item, dict):
            raise typer.BadParameter("--tool-schemas items must be JSON objects.")
        schemas.append(
            ToolSchema(
                name=str(item["name"]),
                description=str(item.get("description", "")),
                input_schema=(
                    dict(item.get("input_schema"))
                    if isinstance(item.get("input_schema"), dict)
                    else {}
                ),
            ),
        )
    return tuple(schemas)


def _profile_settings_to_input(profile: LlmProfileSettings) -> RegisterLlmProfileInput:
    return RegisterLlmProfileInput(
        id=profile.id,
        provider=LlmProviderKind(profile.provider),
        api_family=LlmApiFamily(profile.api_family),
        model_name=profile.model_name,
        context_window_tokens=profile.context_window_tokens,
        model_family=LlmModelFamily(profile.model_family),
        capabilities=tuple(LlmCapability(item) for item in profile.capabilities),
        default_params=LlmDefaults.from_payload(profile.default_params),
        base_url=profile.base_url,
        credential_binding=profile.credential_binding,
        timeout_seconds=profile.timeout_seconds,
        max_concurrency=profile.max_concurrency,
        concurrency_key=profile.concurrency_key,
        source_kind=LlmSourceKind(profile.source_kind),
        enabled=profile.enabled,
    )


def build_cli() -> typer.Typer:
    app = typer.Typer(help="Manage llm profiles and invocations.", no_args_is_help=True)

    @app.command("register-profile")
    def register_profile(
        ctx: typer.Context,
        llm_id: str = typer.Argument(..., help="LLM identifier."),
        provider: LlmProviderKind = typer.Argument(..., help="Provider kind."),
        api_family: LlmApiFamily = typer.Argument(..., help="Adapter API family."),
        model_name: str = typer.Argument(..., help="Model name."),
        context_window_tokens: int | None = typer.Option(
            None,
            help="Optional model context window in tokens.",
        ),
        model_family: LlmModelFamily = typer.Option(
            LlmModelFamily.GENERAL,
            help="Model family.",
        ),
        capability: list[LlmCapability] = typer.Option(
            None,
            "--capability",
            help="Capability flags.",
        ),
        temperature: float | None = typer.Option(None, help="Sampling temperature."),
        top_p: float | None = typer.Option(None, help="Top-p sampling value."),
        max_output_tokens: int | None = typer.Option(
            None,
            help="Maximum output token budget.",
        ),
        reasoning_effort: str | None = typer.Option(
            None,
            help="Reasoning effort hint.",
        ),
        base_url: str | None = typer.Option(None, help="Optional adapter base URL."),
        credential_binding: str | None = typer.Option(
            None,
            help="Credential binding reference.",
        ),
        timeout_seconds: int = typer.Option(60, help="Invocation timeout in seconds."),
        max_concurrency: int | None = typer.Option(
            None,
            "--max-concurrency",
            min=1,
            help="Optional per-concurrency-key LLM invocation limit.",
        ),
        concurrency_key: str | None = typer.Option(
            None,
            "--concurrency-key",
            help="Optional key shared by profiles that should use one LLM limit.",
        ),
        enabled: bool = typer.Option(True, "--enabled/--disabled"),
    ) -> None:
        container = ensure_container(ctx)
        profile = container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id=llm_id,
                provider=provider,
                api_family=api_family,
                model_name=model_name,
                context_window_tokens=context_window_tokens,
                model_family=model_family,
                capabilities=tuple(capability or ()),
                default_params=LlmDefaults(
                    temperature=temperature,
                    top_p=top_p,
                    max_output_tokens=max_output_tokens,
                    reasoning_effort=reasoning_effort,
                ),
                base_url=base_url,
                credential_binding=credential_binding,
                timeout_seconds=timeout_seconds,
                max_concurrency=max_concurrency,
                concurrency_key=concurrency_key,
                enabled=enabled,
            ),
        )
        echo_data(LlmProfileDTO.from_entity(profile))

    @app.command("list")
    def list_profiles(ctx: typer.Context) -> None:
        container = ensure_container(ctx)
        items = [
            LlmProfileDTO.from_entity(profile)
            for profile in container.llm_service.list_profiles()
        ]
        echo_data(items)

    @app.command("sync-profiles")
    def sync_profiles(
        ctx: typer.Context,
        profile: list[str] = typer.Option(
            None,
            "--profile",
            help="Optional configured profile id to sync.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        selected_ids = set(profile or [])
        configured_profiles = tuple(
            item
            for item in container.settings.llm_profiles
            if not selected_ids or item.id in selected_ids
        )
        synced = container.llm_service.sync_profiles(
            tuple(_profile_settings_to_input(item) for item in configured_profiles),
        )
        echo_data([LlmProfileDTO.from_entity(item) for item in synced])

    @app.command("get")
    def get_profile(
        ctx: typer.Context,
        llm_id: str = typer.Argument(..., help="LLM identifier."),
    ) -> None:
        container = ensure_container(ctx)
        echo_data(LlmProfileDTO.from_entity(container.llm_service.get_profile(llm_id)))

    @app.command("invoke")
    def invoke_llm(
        ctx: typer.Context,
        llm_id: str = typer.Argument(..., help="LLM identifier."),
        messages: str = typer.Option(..., help="JSON array of llm messages."),
        tool_schemas: str | None = typer.Option(
            None,
            help="JSON array of tool schemas.",
        ),
        response_format: str | None = typer.Option(
            None,
            help="JSON object describing the expected response format.",
        ),
        overrides: str | None = typer.Option(
            None,
            help="JSON object with provider-specific overrides.",
        ),
    ) -> None:
        container = ensure_container(ctx)
        authorize_llm_action(
            container,
            llm_id=llm_id,
            action="llm.invoke",
            interface_name="cli",
        )
        response_format_payload = _load_json(response_format, "--response-format")
        overrides_payload = _load_json(overrides, "--overrides")
        invocation = container.llm_service.invoke(
            InvokeLlmInput(
                llm_id=llm_id,
                messages=_parse_messages(messages),
                tool_schemas=_parse_tool_schemas(tool_schemas),
                response_format=(
                    dict(response_format_payload)
                    if isinstance(response_format_payload, dict)
                    else None
                ),
                overrides=(
                    dict(overrides_payload)
                    if isinstance(overrides_payload, dict)
                    else {}
                ),
            ),
        )
        echo_data(LlmInvocationDTO.from_entity(invocation))

    @app.command("invocations")
    def list_invocations(
        ctx: typer.Context,
        llm_id: str | None = typer.Option(None, help="Optional LLM identifier."),
    ) -> None:
        container = ensure_container(ctx)
        items = [
            LlmInvocationDTO.from_entity(invocation)
            for invocation in container.llm_service.list_invocations(llm_id=llm_id)
        ]
        echo_data(items)

    @app.command("get-invocation")
    def get_invocation(
        ctx: typer.Context,
        invocation_id: str = typer.Argument(..., help="Invocation identifier."),
    ) -> None:
        container = ensure_container(ctx)
        invocation = container.llm_service.get_invocation(invocation_id)
        echo_data(LlmInvocationDTO.from_entity(invocation))

    return app
