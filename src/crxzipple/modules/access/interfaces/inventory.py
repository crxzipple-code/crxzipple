from __future__ import annotations

import hashlib
import re
from typing import Any

from crxzipple.modules.access.application import (
    canonical_credential_binding,
    is_codex_auth_json_binding,
    is_credential_binding,
    parse_access_requirement,
)
from crxzipple.modules.access.interfaces.presenters import present_readiness

AuthorizationCheckSpec = tuple[str, str, bool]

_CREDENTIAL_REQUIREMENT_KINDS = {"api_key", "bearer", "basic", "credential"}


def collect_access_inventory(
    container: Any,
    *,
    workspace_dir: str | None = None,
    include_ready: bool = False,
    include_disabled: bool = False,
) -> dict[str, object]:
    targets: list[dict[str, object]] = []
    groups = _collect_authorization_groups(
        container,
        include_disabled=include_disabled,
    )
    for group in sorted(groups.values(), key=_authorization_sort_key):
        specs = tuple(group["check_specs"])
        checks = _authorization_checks(
            container,
            specs,
            workspace_dir=workspace_dir,
        )
        target = _target_payload(
            resource_type="authorization",
            resource_id=_authorization_resource_id(specs),
            display_name=_authorization_display_name(specs, group),
            requirement_sets=(checks,),
            metadata=_authorization_metadata(specs, group),
        )
        if include_ready or not target["ready"]:
            targets.append(target)

    ready_targets = [target for target in targets if bool(target.get("ready"))]
    return {
        "ready": len(ready_targets) == len(targets),
        "targets": targets,
        "counts": {
            "total": len(targets),
            "ready": len(ready_targets),
            "blocked": len(targets) - len(ready_targets),
        },
    }


def _collect_authorization_groups(
    container: Any,
    *,
    include_disabled: bool,
) -> dict[tuple[AuthorizationCheckSpec, ...], dict[str, object]]:
    groups: dict[tuple[AuthorizationCheckSpec, ...], dict[str, object]] = {}
    _collect_llm_authorization_usages(
        groups,
        container,
        include_disabled=include_disabled,
    )
    _collect_tool_authorization_usages(
        groups,
        container,
        include_disabled=include_disabled,
    )
    _collect_channel_authorization_usages(
        groups,
        container,
        include_disabled=include_disabled,
    )
    return groups


def _collect_llm_authorization_usages(
    groups: dict[tuple[AuthorizationCheckSpec, ...], dict[str, object]],
    container: Any,
    *,
    include_disabled: bool,
) -> None:
    for profile in container.llm_service.list_profiles():
        if not profile.enabled and not include_disabled:
            continue
        binding = (
            profile.credential_binding.strip()
            if isinstance(profile.credential_binding, str)
            else ""
        )
        if not binding:
            continue
        if not is_credential_binding(binding):
            continue
        _add_authorization_usage(
            groups,
            (("credential_binding", binding, True),),
            {
                "usage_type": "llm_profile",
                "usage_id": profile.id,
                "display_name": profile.model_name,
                "enabled": profile.enabled,
                "provider": profile.provider.value,
                "api_family": profile.api_family.value,
                "base_url": profile.base_url,
                "credential_binding": binding,
            },
        )


def _collect_tool_authorization_usages(
    groups: dict[tuple[AuthorizationCheckSpec, ...], dict[str, object]],
    container: Any,
    *,
    include_disabled: bool,
) -> None:
    tools = (
        container.tool_service.list_tools()
        if include_disabled
        else container.tool_service.list_enabled_tools()
    )
    for tool in tools:
        requirement_sets = tuple(tool.access_requirement_sets)
        if not requirement_sets:
            continue
        for requirement_set in requirement_sets:
            _add_authorization_usage(
                groups,
                tuple(("requirement", str(item), False) for item in requirement_set),
                {
                    "usage_type": "tool",
                    "usage_id": tool.id,
                    "display_name": tool.name,
                    "enabled": tool.enabled,
                    "source_kind": tool.source_kind.value,
                    "access_requirement_set": list(requirement_set),
                },
            )


def _collect_channel_authorization_usages(
    groups: dict[tuple[AuthorizationCheckSpec, ...], dict[str, object]],
    container: Any,
    *,
    include_disabled: bool,
) -> None:
    for profile in container.channel_profile_service.list_profiles():
        if not profile.enabled and not include_disabled:
            continue
        requirements = _channel_profile_access_requirements(container, profile)
        if not requirements:
            continue
        _add_authorization_usage(
            groups,
            tuple(("requirement", item, False) for item in requirements),
            {
                "usage_type": "channel_profile",
                "usage_id": profile.channel_type,
                "display_name": profile.channel_type,
                "enabled": profile.enabled,
                "account_count": len(profile.accounts),
                "access_requirements": list(requirements),
            },
        )


def _add_authorization_usage(
    groups: dict[tuple[AuthorizationCheckSpec, ...], dict[str, object]],
    check_specs: tuple[AuthorizationCheckSpec, ...],
    usage: dict[str, object],
) -> None:
    key = _authorization_key(check_specs)
    if not key:
        return
    group = groups.setdefault(key, {"check_specs": key, "usages": []})
    usages = group["usages"]
    if isinstance(usages, list):
        usages.append(dict(usage))


def _authorization_key(
    check_specs: tuple[AuthorizationCheckSpec, ...],
) -> tuple[AuthorizationCheckSpec, ...]:
    return tuple(
        sorted(
            canonical
            for target_type, raw, allow_literal in check_specs
            if (canonical := _canonical_check_spec(target_type, raw, allow_literal))
            is not None
        ),
    )


def _canonical_check_spec(
    target_type: str,
    raw: str,
    allow_literal: bool,
) -> AuthorizationCheckSpec | None:
    normalized = raw.strip()
    if not normalized:
        return None
    if target_type == "credential_binding":
        return _credential_binding_check_spec(
            normalized,
            allow_literal=allow_literal,
        )

    binding = _credential_binding_for_requirement(normalized)
    if binding is not None:
        return _credential_binding_check_spec(binding, allow_literal=False)
    return ("requirement", normalized, False)


def _credential_binding_for_requirement(requirement: str) -> str | None:
    normalized = requirement.strip()
    if is_credential_binding(normalized):
        return normalized
    parsed = parse_access_requirement(normalized)
    if parsed.kind not in _CREDENTIAL_REQUIREMENT_KINDS or len(parsed.scopes) != 1:
        return None
    candidate = parsed.scopes[0].strip()
    if is_credential_binding(candidate):
        return candidate
    return None


def _credential_binding_check_spec(
    binding: str,
    *,
    allow_literal: bool,
) -> AuthorizationCheckSpec:
    canonical = canonical_credential_binding(binding)
    return (
        "credential_binding",
        canonical,
        allow_literal and not is_credential_binding(canonical),
    )


def _authorization_checks(
    container: Any,
    specs: tuple[AuthorizationCheckSpec, ...],
    *,
    workspace_dir: str | None,
) -> tuple[dict[str, object], ...]:
    checks: list[dict[str, object]] = []
    for target_type, raw, allow_literal in specs:
        if target_type == "credential_binding":
            readiness = container.access_service.check_credential_binding(
                raw,
                workspace_dir=workspace_dir,
                allow_literal=allow_literal,
            )
        else:
            readiness = container.access_service.check_requirement(
                raw,
                workspace_dir=workspace_dir,
            )
        checks.append(present_readiness(readiness, target_type=target_type))
    return tuple(checks)


def _authorization_sort_key(group: dict[str, object]) -> tuple[str, str]:
    specs = tuple(group["check_specs"])
    display_name = _authorization_display_name(specs, group)
    return (display_name.lower(), _authorization_resource_id(specs))


def _channel_profile_access_requirements(container: Any, profile: Any) -> tuple[str, ...]:
    channel_type = str(profile.channel_type).strip().lower()
    if channel_type == "lark":
        return container.lark_channel_runtime_service.profile_access_requirements(profile)
    if channel_type == "web":
        return container.web_channel_runtime_service.profile_access_requirements(profile)
    if channel_type == "webhook":
        return container.webhook_channel_runtime_service.profile_access_requirements(
            profile,
        )
    return container.webhook_channel_runtime_service.profile_access_requirements(profile)


def _authorization_display_name(
    specs: tuple[AuthorizationCheckSpec, ...],
    _group: dict[str, object],
) -> str:
    labels = [_authorization_check_label(target_type, raw) for target_type, raw, _ in specs]
    if len(labels) == 1:
        return labels[0]
    return " + ".join(labels)


def _authorization_resource_id(specs: tuple[AuthorizationCheckSpec, ...]) -> str:
    raw = "|".join(
        f"{target_type}:{allow_literal}:{requirement}"
        for target_type, requirement, allow_literal in specs
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    prefix = _slugify(
        "+".join(
            _authorization_check_label(target_type, requirement)
            for target_type, requirement, _ in specs
        ),
    )
    return f"authorization:{prefix}:{digest}"


def _authorization_metadata(
    specs: tuple[AuthorizationCheckSpec, ...],
    group: dict[str, object],
) -> dict[str, object]:
    usages = _authorization_usages(group)
    enabled_count = sum(1 for usage in usages if bool(usage.get("enabled")))
    disabled_count = len(usages) - enabled_count
    metadata: dict[str, object] = {
        "asset_kind": _authorization_asset_kind(specs),
        "requirements": [raw for _, raw, _ in specs],
        "check_types": [target_type for target_type, _, _ in specs],
        "labels": [
            _authorization_check_label(target_type, raw)
            for target_type, raw, _ in specs
        ],
        "usage_count": len(usages),
        "enabled_usage_count": enabled_count,
        "disabled_usage_count": disabled_count,
        "usage_types": sorted(
            {
                str(usage.get("usage_type"))
                for usage in usages
                if usage.get("usage_type")
            },
        ),
        "usages": usages,
    }
    declared = _declared_access_values(usages)
    if declared:
        metadata["declared_requirements"] = declared
    _add_usage_summary(metadata, usages)
    return metadata


def _authorization_asset_kind(specs: tuple[AuthorizationCheckSpec, ...]) -> str:
    if len(specs) != 1:
        return "credential_set"
    target_type, raw, _ = specs[0]
    if target_type == "credential_binding":
        return _credential_asset_kind(raw)
    return "authorization_requirement"


def _credential_asset_kind(binding: str) -> str:
    normalized = binding.strip()
    if normalized.startswith("env:"):
        return "env"
    if normalized.startswith("file:"):
        return "file"
    if is_codex_auth_json_binding(normalized):
        return "codex_auth_json"
    return "inline_credential"


def _authorization_usages(group: dict[str, object]) -> list[dict[str, object]]:
    raw_usages = group.get("usages")
    if not isinstance(raw_usages, list):
        return []
    by_key: dict[tuple[str, str], dict[str, object]] = {}
    for raw_usage in raw_usages:
        if not isinstance(raw_usage, dict):
            continue
        usage = dict(raw_usage)
        key = (
            str(usage.get("usage_type") or ""),
            str(usage.get("usage_id") or ""),
        )
        by_key[key] = usage
    return [by_key[key] for key in sorted(by_key)]


def _declared_access_values(usages: list[dict[str, object]]) -> list[str]:
    values: set[str] = set()
    for usage in usages:
        binding = usage.get("credential_binding")
        if isinstance(binding, str) and binding.strip():
            values.add(binding.strip())
        for field in ("access_requirement_set", "access_requirements"):
            raw_values = usage.get(field)
            if not isinstance(raw_values, (list, tuple)):
                continue
            for raw_value in raw_values:
                if isinstance(raw_value, str) and raw_value.strip():
                    values.add(raw_value.strip())
    return sorted(values)


def _add_usage_summary(
    metadata: dict[str, object],
    usages: list[dict[str, object]],
) -> None:
    llm_profile_ids = _usage_values(usages, "llm_profile", "usage_id")
    model_names = _usage_values(usages, "llm_profile", "display_name")
    tool_ids = _usage_values(usages, "tool", "usage_id")
    channel_profiles = _usage_values(usages, "channel_profile", "usage_id")
    if llm_profile_ids:
        metadata["llm_profile_ids"] = llm_profile_ids
    if model_names:
        metadata["model_names"] = model_names
    if tool_ids:
        metadata["tool_ids"] = tool_ids
    if channel_profiles:
        metadata["channel_profiles"] = channel_profiles


def _usage_values(
    usages: list[dict[str, object]],
    usage_type: str,
    field: str,
) -> list[str]:
    return sorted(
        {
            str(usage.get(field))
            for usage in usages
            if usage.get("usage_type") == usage_type and usage.get(field)
        },
    )


def _authorization_check_label(target_type: str, raw: str) -> str:
    normalized = raw.strip()
    if normalized.startswith("env:"):
        env_name = normalized.removeprefix("env:").strip()
        return env_name or "env"
    if normalized.startswith("file:"):
        path = normalized.removeprefix("file:").strip()
        return f"file:{path}" if path else "file credential"
    if target_type == "credential_binding":
        return _credential_binding_label(normalized)
    return normalized


def _credential_binding_label(binding: str) -> str:
    normalized = binding.strip()
    if normalized.startswith("env:"):
        env_name = normalized.removeprefix("env:").strip()
        return f"env:{env_name}" if env_name else "env"
    if normalized.startswith("file:"):
        return "file credential"
    if is_codex_auth_json_binding(normalized):
        canonical = canonical_credential_binding(normalized)
        return canonical if ":" in canonical else "codex_auth_json"
    return "inline credential"


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip())
    return normalized.strip("-") or "default"


def _target_payload(
    *,
    resource_type: str,
    resource_id: str,
    display_name: str | None,
    requirement_sets: tuple[tuple[dict[str, object], ...], ...],
    metadata: dict[str, object],
) -> dict[str, object]:
    set_payloads = tuple(_requirement_set_payload(items) for items in requirement_sets)
    ready = any(bool(item["ready"]) for item in set_payloads) if set_payloads else True
    missing_checks = [
        check
        for item in set_payloads
        for check in item["checks"]
        if isinstance(check, dict) and not bool(check.get("ready"))
    ]
    return {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "display_name": display_name,
        "ready": ready,
        "setup_available": (not ready) and any(
            bool(check.get("setup_available")) for check in missing_checks
        ),
        "requirement_sets": list(set_payloads),
        "metadata": dict(metadata),
    }


def _requirement_set_payload(
    checks: tuple[dict[str, object], ...],
) -> dict[str, object]:
    return {
        "ready": all(bool(check.get("ready")) for check in checks),
        "checks": [dict(check) for check in checks],
    }
