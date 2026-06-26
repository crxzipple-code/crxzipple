from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from crxzipple.modules.settings.application.materialization_models import (
    SettingsMaterializationWarning,
)
from crxzipple.modules.settings.application.materialization_payloads import (
    access_config_from_payload,
    legacy_agent_profile_payload,
    legacy_channel_profile_payload,
    legacy_llm_profile_payload,
    tool_provider_from_payload,
    tool_root_from_payload,
    with_default_id,
)
from crxzipple.modules.settings.application.services import SettingsQueryService
from crxzipple.shared.settings import (
    AccessConfig,
    MemoryConfig,
    RuntimeDefaultsConfig,
    ToolProviderConfig,
    ToolRootConfig,
)


JsonObject = dict[str, Any]
ConfigT = TypeVar("ConfigT")


class SettingsEffectiveConfigMaterializer:
    def __init__(
        self,
        query_service: SettingsQueryService,
        *,
        environment: str | None = None,
    ) -> None:
        self._queries = query_service
        self._environment = environment
        self._warnings: list[SettingsMaterializationWarning] = []
        self._effective_payload_cache: dict[
            str,
            tuple[tuple[str, Mapping[str, Any]], ...],
        ] = {}

    @property
    def warnings(self) -> tuple[SettingsMaterializationWarning, ...]:
        return tuple(self._warnings)

    def clear_warnings(self) -> None:
        self._warnings.clear()

    def clear_cache(self) -> None:
        self._effective_payload_cache.clear()

    def legacy_llm_profile_payloads(self) -> tuple[JsonObject, ...]:
        return self._materialize_many(
            "llm-profiles",
            legacy_llm_profile_payload,
        )

    def legacy_agent_profile_payloads(self) -> tuple[JsonObject, ...]:
        return self._materialize_many_from_kinds(
            ("agent_profile", "agent-profile", "agent-profiles"),
            legacy_agent_profile_payload,
        )

    def tool_providers(self) -> tuple[ToolProviderConfig, ...]:
        return self._materialize_many(
            "tool-catalog",
            tool_provider_from_payload,
        )

    def tool_roots(self) -> tuple[ToolRootConfig, ...]:
        return self._materialize_many(
            "tool-catalog",
            tool_root_from_payload,
        )

    def legacy_channel_profile_payloads(self) -> tuple[JsonObject, ...]:
        return self._materialize_many(
            "channel-profiles",
            legacy_channel_profile_payload,
        )

    def memory_config(self) -> MemoryConfig | None:
        return self._materialize_one(
            "memory-config",
            lambda resource_id, payload: MemoryConfig.from_payload(
                with_default_id(payload, "config_id", resource_id or "default"),
            ),
        )

    def runtime_defaults(self) -> RuntimeDefaultsConfig | None:
        return self._materialize_one(
            "runtime-defaults",
            lambda resource_id, payload: RuntimeDefaultsConfig.from_payload(
                with_default_id(payload, "config_id", resource_id or "defaults"),
            ),
        )

    def access_configs(self) -> tuple[AccessConfig, ...]:
        return self._materialize_many(
            "access-assets",
            access_config_from_payload,
        )

    def _materialize_one(
        self,
        resource_kind: str,
        parser: Callable[[str, Mapping[str, Any]], ConfigT | None],
    ) -> ConfigT | None:
        values = self._materialize_many(resource_kind, parser)
        return values[0] if values else None

    def _materialize_many(
        self,
        resource_kind: str,
        parser: Callable[[str, Mapping[str, Any]], ConfigT | None],
    ) -> tuple[ConfigT, ...]:
        values: list[ConfigT] = []
        for resource_id, payload in self._effective_payloads_for_kind(resource_kind):
            try:
                value = parser(resource_id, payload)
            except Exception as exc:
                self._warn(
                    resource_kind=resource_kind,
                    resource_id=resource_id,
                    code="invalid_effective_payload",
                    message=str(exc),
                )
                continue
            if value is not None:
                values.append(value)
        return tuple(values)

    def _effective_payloads_for_kind(
        self,
        resource_kind: str,
    ) -> tuple[tuple[str, Mapping[str, Any]], ...]:
        cached = self._effective_payload_cache.get(resource_kind)
        if cached is not None:
            return cached

        payloads: list[tuple[str, Mapping[str, Any]]] = []
        for resource_id, payload in self._queries.list_effective_payloads(
            resource_kind=resource_kind,
            environment=self._environment,
        ):
            try:
                if not isinstance(payload, Mapping):
                    raise ValueError("effective payload must be an object.")
            except Exception as exc:
                self._warn(
                    resource_kind=resource_kind,
                    resource_id=resource_id,
                    code="invalid_effective_payload",
                    message=str(exc),
                )
                continue
            payloads.append((resource_id, payload))
        resolved = tuple(payloads)
        self._effective_payload_cache[resource_kind] = resolved
        return resolved

    def _materialize_many_from_kinds(
        self,
        resource_kinds: tuple[str, ...],
        parser: Callable[[str, Mapping[str, Any]], ConfigT | None],
    ) -> tuple[ConfigT, ...]:
        values: list[ConfigT] = []
        seen_resource_ids: set[str] = set()
        for resource_kind in resource_kinds:
            for value in self._materialize_many(resource_kind, parser):
                resource_id = (
                    value.get("profile_id")
                    if isinstance(value, Mapping)
                    else getattr(value, "profile_id", None)
                )
                if not isinstance(resource_id, str) or not resource_id:
                    values.append(value)
                    continue
                if resource_id in seen_resource_ids:
                    continue
                seen_resource_ids.add(resource_id)
                values.append(value)
        return tuple(values)

    def _warn(
        self,
        *,
        resource_kind: str,
        resource_id: str,
        code: str,
        message: str,
    ) -> None:
        self._warnings.append(
            SettingsMaterializationWarning(
                resource_kind=resource_kind,
                resource_id=resource_id,
                code=code,
                message=message,
            ),
        )
