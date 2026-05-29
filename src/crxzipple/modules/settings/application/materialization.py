from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

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


@dataclass(frozen=True, slots=True)
class SettingsMaterializationWarning:
    resource_kind: str
    resource_id: str
    code: str
    message: str

    def to_payload(self) -> JsonObject:
        return {
            "resource_kind": self.resource_kind,
            "resource_id": self.resource_id,
            "code": self.code,
            "message": self.message,
        }


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

    @property
    def warnings(self) -> tuple[SettingsMaterializationWarning, ...]:
        return tuple(self._warnings)

    def clear_warnings(self) -> None:
        self._warnings.clear()

    def legacy_llm_profile_payloads(self) -> tuple[JsonObject, ...]:
        return self._materialize_many(
            "llm-profiles",
            _legacy_llm_profile_payload,
        )

    def legacy_agent_profile_payloads(self) -> tuple[JsonObject, ...]:
        return self._materialize_many_from_kinds(
            ("agent_profile", "agent-profile", "agent-profiles"),
            _legacy_agent_profile_payload,
        )

    def tool_providers(self) -> tuple[ToolProviderConfig, ...]:
        return self._materialize_many(
            "tool-catalog",
            self._tool_provider_from_payload,
        )

    def tool_roots(self) -> tuple[ToolRootConfig, ...]:
        return self._materialize_many(
            "tool-catalog",
            self._tool_root_from_payload,
        )

    def legacy_channel_profile_payloads(self) -> tuple[JsonObject, ...]:
        return self._materialize_many(
            "channel-profiles",
            _legacy_channel_profile_payload,
        )

    def memory_config(self) -> MemoryConfig | None:
        return self._materialize_one(
            "memory-config",
            lambda resource_id, payload: MemoryConfig.from_payload(
                _with_default_id(payload, "config_id", resource_id or "default"),
            ),
        )

    def runtime_defaults(self) -> RuntimeDefaultsConfig | None:
        return self._materialize_one(
            "runtime-defaults",
            lambda resource_id, payload: RuntimeDefaultsConfig.from_payload(
                _with_default_id(payload, "config_id", resource_id or "defaults"),
            ),
        )

    def access_configs(self) -> tuple[AccessConfig, ...]:
        return self._materialize_many(
            "access-assets",
            self._access_config_from_payload,
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
        for resource in self._queries.list_resources(resource_kind=resource_kind):
            try:
                resolution = self._queries.get_effective(
                    resource.id,
                    environment=self._environment,
                )
                payload = resolution.effective_value
                if not isinstance(payload, Mapping):
                    raise ValueError("effective payload must be an object.")
                value = parser(resource.id, payload)
            except Exception as exc:
                self._warn(
                    resource_kind=resource_kind,
                    resource_id=resource.id,
                    code="invalid_effective_payload",
                    message=str(exc),
                )
                continue
            if value is not None:
                values.append(value)
        return tuple(values)

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

    def _tool_provider_from_payload(
        self,
        resource_id: str,
        payload: Mapping[str, Any],
    ) -> ToolProviderConfig | None:
        provider_kind = str(
            payload.get("provider_kind") or payload.get("kind") or ""
        ).strip()
        if provider_kind in {"", "local_root"}:
            return None
        default_provider_id = str(payload.get("name") or resource_id)
        normalized = _with_default_id(payload, "provider_id", default_provider_id)
        if (
            normalized.get("spec_path") is None
            and normalized.get("spec_location") is not None
        ):
            normalized["spec_path"] = normalized["spec_location"]
        return ToolProviderConfig.from_payload(normalized)

    def _tool_root_from_payload(
        self,
        resource_id: str,
        payload: Mapping[str, Any],
    ) -> ToolRootConfig | None:
        provider_kind = str(
            payload.get("provider_kind") or payload.get("kind") or ""
        ).strip()
        if provider_kind not in {"", "local_root"}:
            return None
        if payload.get("path") is None:
            return None
        normalized = _with_default_id(payload, "root_id", resource_id)
        normalized.setdefault("source_kind", "local")
        return ToolRootConfig.from_payload(normalized)

    def _access_config_from_payload(
        self,
        resource_id: str,
        payload: Mapping[str, Any],
    ) -> AccessConfig:
        normalized = _normalize_access_payload(resource_id, payload)
        return AccessConfig.from_payload(normalized)

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


def _with_default_id(
    payload: Mapping[str, Any],
    field_name: str,
    resource_id: str,
) -> JsonObject:
    normalized = dict(payload)
    normalized.setdefault(field_name, resource_id)
    normalized.setdefault("id", resource_id)
    return normalized


def _legacy_llm_profile_payload(
    resource_id: str,
    payload: Mapping[str, Any],
) -> JsonObject:
    normalized = _with_default_id(payload, "profile_id", resource_id)
    if normalized.get("model_name") is None and normalized.get("model") is not None:
        normalized["model_name"] = normalized["model"]
    for field_name in ("provider", "api_family", "model_name"):
        _required_legacy_text(normalized.get(field_name), field_name=field_name)
    return normalized


def _legacy_agent_profile_payload(
    resource_id: str,
    payload: Mapping[str, Any],
) -> JsonObject:
    return _with_default_id(payload, "profile_id", resource_id)


def _legacy_channel_profile_payload(
    resource_id: str,
    payload: Mapping[str, Any],
) -> JsonObject:
    normalized = _normalize_channel_payload(resource_id, payload)
    normalized.setdefault("id", resource_id)
    return normalized


def _required_legacy_text(value: object, *, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required.")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _normalize_channel_payload(
    resource_id: str, payload: Mapping[str, Any]
) -> JsonObject:
    normalized = _with_default_id(payload, "profile_id", resource_id)
    if (
        normalized.get("channel_kind") is None
        and normalized.get("channel_type") is not None
    ):
        normalized["channel_kind"] = normalized["channel_type"]
    return normalized


def _normalize_access_payload(
    resource_id: str, payload: Mapping[str, Any]
) -> JsonObject:
    normalized = _with_default_id(payload, "config_id", resource_id)
    declaration_kind = str(
        normalized.get("access_declaration_kind")
        or normalized.get("declaration_kind")
        or normalized.get("resource_type")
        or "",
    ).strip()
    if declaration_kind in {"asset", "access_asset"}:
        normalized.setdefault("assets", (_without_declaration_kind(normalized),))
    elif declaration_kind in {"credential_binding", "credential"}:
        normalized.setdefault(
            "credential_bindings",
            (_without_declaration_kind(normalized),),
        )
    elif declaration_kind in {"consumer_binding", "consumer"}:
        normalized.setdefault(
            "consumer_bindings",
            (_without_declaration_kind(normalized),),
        )
    elif declaration_kind in {"provider_scope_enablement", "provider_scope"}:
        normalized.setdefault(
            "provider_scope_enablements",
            (_without_declaration_kind(normalized),),
        )
    elif declaration_kind in {"permission_enablement", "permission"}:
        normalized.setdefault(
            "permission_enablements",
            (_without_declaration_kind(normalized),),
        )
    return normalized


def _without_declaration_kind(payload: Mapping[str, Any]) -> JsonObject:
    return {
        str(key): value
        for key, value in payload.items()
        if key
        not in {
            "access_declaration_kind",
            "declaration_kind",
            "resource_type",
            "config_id",
            "id",
        }
    }
