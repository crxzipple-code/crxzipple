from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.access.application.memory_consumers import (
    memory_access_consumer_bindings,
)
from crxzipple.modules.access.application.read_models import (
    AccessConsumerBindingReadModel,
)
from crxzipple.modules.tool.application import ToolFunctionStatus


def external_access_consumer_bindings(
    container: Any,
) -> tuple[AccessConsumerBindingReadModel, ...]:
    return (
        _memory_credential_consumers(container)
        + _tool_credential_consumers(container)
        + _channel_credential_consumers(container)
        + _browser_proxy_consumers(container)
    )


def _memory_credential_consumers(
    container: Any,
) -> tuple[AccessConsumerBindingReadModel, ...]:
    try:
        config = container.require("memory.bootstrap_config")
    except Exception:
        return ()
    return memory_access_consumer_bindings(config)


def _tool_credential_consumers(
    container: Any,
) -> tuple[AccessConsumerBindingReadModel, ...]:
    try:
        source_query = container.require("tool.source_query_service")
        functions = source_query.list_functions()
    except Exception:
        return ()
    consumers: list[AccessConsumerBindingReadModel] = []
    for function in functions:
        if not _active_tool_function(function):
            continue
        requirement_sets, credential_bindings = _tool_function_requirement_sets(
            function,
        )
        if not requirement_sets:
            continue
        consumers.append(
            AccessConsumerBindingReadModel(
                binding_id=f"tool:function:{function.function_id}:credentials",
                consumer_module="tool",
                consumer_kind="tool",
                consumer_id=function.function_id,
                display_name=function.name,
                enabled=bool(function.enabled),
                credential_binding_id=_primary_binding_id(credential_bindings),
                credential_bindings=credential_bindings,
                requirement_sets=requirement_sets,
                status="active",
                metadata={
                    "source": "tool.function_catalog",
                    "source_id": function.source_id,
                    "function_id": function.function_id,
                    "function_revision": function.revision,
                    "schema_hash": function.schema_hash,
                    "runtime_kind": str(function.runtime_kind),
                },
                created_at=function.created_at,
                updated_at=function.updated_at,
            ),
        )
    return tuple(consumers)


def _channel_credential_consumers(
    container: Any,
) -> tuple[AccessConsumerBindingReadModel, ...]:
    try:
        profile_service = container.require("channels.profile_service")
        profiles = profile_service.list_profiles()
    except Exception:
        return ()

    consumers: list[AccessConsumerBindingReadModel] = []
    for profile in profiles:
        channel_type = _text(getattr(profile, "channel_type", ""))
        if not channel_type:
            continue
        profile_enabled = bool(getattr(profile, "enabled", True))
        for account in tuple(getattr(profile, "accounts", ()) or ()):
            account_id = _text(getattr(account, "account_id", ""))
            if not account_id:
                continue
            credential_bindings = _mapping(getattr(account, "credential_bindings", {}))
            requirement_refs = _channel_requirement_refs(account, credential_bindings)
            if not requirement_refs:
                continue
            account_enabled = bool(getattr(account, "enabled", True))
            consumer_id = f"channels.{channel_type.strip().lower()}.account:{account_id}"
            consumers.append(
                AccessConsumerBindingReadModel(
                    binding_id=f"channel:account:{channel_type}:{account_id}:credentials",
                    consumer_module="channels",
                    consumer_kind="channel_account",
                    consumer_id=consumer_id,
                    display_name=f"{channel_type} / {account_id}",
                    enabled=profile_enabled and account_enabled,
                    credential_binding_id=_primary_binding_id(credential_bindings),
                    credential_bindings=credential_bindings,
                    requirement_sets=(requirement_refs,),
                    status="active" if profile_enabled and account_enabled else "disabled",
                    metadata={
                        "source": "channels.profile_service",
                        "channel_type": channel_type,
                        "channel_account_id": account_id,
                    },
                ),
            )
    return tuple(consumers)


def _browser_proxy_consumers(
    container: Any,
) -> tuple[AccessConsumerBindingReadModel, ...]:
    try:
        profile_service = container.require("browser.query_service")
        profiles = profile_service.list_profiles()
    except Exception:
        return ()

    consumers: list[AccessConsumerBindingReadModel] = []
    for profile in profiles:
        profile_name = _text(getattr(profile, "name", ""))
        proxy_mode = _text(getattr(profile, "proxy_mode", "")).lower()
        if not profile_name or proxy_mode != "access_binding":
            continue
        binding_id = _text(getattr(profile, "proxy_binding_id", ""))
        credential_kind = _text(getattr(profile, "proxy_credential_kind", "")) or "basic"
        if credential_kind == "bearer":
            credential_kind = "bearer_token"
        credential_bindings = {"proxy": binding_id} if binding_id else {}
        consumers.append(
            AccessConsumerBindingReadModel(
                binding_id=f"browser:profile:{profile_name}:proxy",
                consumer_module="browser",
                consumer_kind="browser_profile_proxy",
                consumer_id=f"browser.profile:{profile_name}:proxy",
                display_name=f"Browser proxy / {profile_name}",
                enabled=True,
                credential_binding_id=binding_id or None,
                credential_bindings=credential_bindings,
                requirement_sets=((f"browser_proxy:{credential_kind}(proxy)",),),
                status="active",
                metadata={
                    "source": "browser.profile_query_service",
                    "profile_name": profile_name,
                    "proxy_mode": proxy_mode,
                    "proxy_credential_kind": credential_kind,
                },
            ),
        )
    return tuple(consumers)


def _channel_requirement_refs(
    account: object,
    credential_bindings: Mapping[str, str],
) -> tuple[str, ...]:
    requirement_set = getattr(account, "credential_requirements", None)
    requirements = tuple(getattr(requirement_set, "requirements", ()) or ())
    refs: list[str] = []
    for requirement in requirements:
        slot = getattr(requirement, "slot", None)
        slot_id = _text(getattr(slot, "slot", ""))
        if not slot_id:
            continue
        required = bool(getattr(slot, "required", True))
        if not required and slot_id not in credential_bindings:
            continue
        expected_kind = _enum_text(getattr(slot, "expected_kind", "api_key"))
        provider = _text(getattr(requirement, "provider", ""))
        body = f"{expected_kind or 'api_key'}({slot_id})"
        refs.append(f"{provider}:{body}" if provider else body)
    return tuple(refs)


def _active_tool_function(function: object) -> bool:
    try:
        status = ToolFunctionStatus(str(getattr(function, "status")))
    except ValueError:
        return False
    return bool(getattr(function, "enabled", False)) and status is ToolFunctionStatus.ACTIVE


def _tool_function_requirement_sets(
    function: object,
) -> tuple[tuple[tuple[str, ...], ...], dict[str, str]]:
    requirement_sets: list[tuple[str, ...]] = []
    credential_bindings: dict[str, str] = {}
    overrides = _mapping(getattr(function, "credential_binding_overrides", {}))
    requirements = getattr(function, "requirements", None)
    credential_requirements = tuple(
        getattr(requirements, "credential_requirements", ()) if requirements else (),
    )
    for requirement_set in credential_requirements:
        refs: list[str] = []
        for requirement in tuple(getattr(requirement_set, "requirements", ())):
            slot = getattr(requirement, "slot", None)
            slot_id = _text(getattr(slot, "slot", ""))
            if not slot_id:
                continue
            refs.append(_credential_requirement_ref(requirement))
            binding_id = _text(
                overrides.get(slot_id) or getattr(slot, "binding_id", "") or "",
            )
            if binding_id:
                credential_bindings[slot_id] = binding_id
        if refs:
            requirement_sets.append(tuple(refs))
    return tuple(requirement_sets), credential_bindings


def _credential_requirement_ref(requirement: object) -> str:
    slot = getattr(requirement, "slot", None)
    slot_id = _text(getattr(slot, "slot", ""))
    expected_kind = _enum_text(getattr(slot, "expected_kind", "api_key"))
    body = f"{expected_kind or 'api_key'}({slot_id})"
    provider = _text(getattr(requirement, "provider", ""))
    return f"{provider}:{body}" if provider else body


def _primary_binding_id(bindings: Mapping[str, str]) -> str | None:
    if len(bindings) != 1:
        return None
    return next(iter(bindings.values()))


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _enum_text(value: object) -> str:
    return _text(getattr(value, "value", value))


def _text(value: object) -> str:
    return str(value or "").strip()
