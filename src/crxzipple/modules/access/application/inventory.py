from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Mapping, Protocol

from crxzipple.modules.access.application.inventory_redaction import (
    sanitize_access_metadata,
)
from crxzipple.modules.access.application.inventory_requirement_rules import (
    AccessReadinessCheckSpec,
    access_check_label,
    credential_asset_kind,
    credential_binding_check_spec,
    credential_binding_for_requirement,
    is_credential_binding,
    masked_inventory_requirement,
)
from crxzipple.modules.access.application.read_models import (
    AccessAssetDetailReadModel,
    AccessConsumerBindingReadModel,
    CredentialBindingReadModel,
)


class AccessInventoryReadinessChecker(Protocol):
    def __call__(
        self,
        specs: tuple[AccessReadinessCheckSpec, ...],
    ) -> tuple[Mapping[str, object], ...]: ...


@dataclass(frozen=True, slots=True)
class AccessInventoryInput:
    assets: tuple[AccessAssetDetailReadModel, ...] = ()
    credential_bindings: tuple[CredentialBindingReadModel, ...] = ()
    consumer_bindings: tuple[AccessConsumerBindingReadModel, ...] = ()


def collect_access_inventory_from_read_models(
    source: AccessInventoryInput,
    *,
    check_readiness: AccessInventoryReadinessChecker,
    include_ready: bool = False,
    include_disabled: bool = False,
) -> dict[str, object]:
    groups = _collect_access_requirement_groups_from_read_models(
        source,
        include_disabled=include_disabled,
    )
    targets: list[dict[str, object]] = []
    for group in sorted(groups.values(), key=_access_requirement_sort_key):
        specs = tuple(group["check_specs"])
        checks = tuple(dict(check) for check in check_readiness(specs))
        target = _target_payload(
            resource_type="access_requirement",
            resource_id=str(group.get("resource_id") or _access_requirement_id(specs)),
            display_name=str(
                group.get("display_name") or _access_requirement_display_name(specs),
            ),
            requirement_sets=(checks,),
            metadata=_access_requirement_metadata(specs, group),
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


def _collect_access_requirement_groups_from_read_models(
    source: AccessInventoryInput,
    *,
    include_disabled: bool,
) -> dict[tuple[AccessReadinessCheckSpec, ...], dict[str, object]]:
    groups: dict[tuple[AccessReadinessCheckSpec, ...], dict[str, object]] = {}
    assets = {asset.asset_id: asset for asset in source.assets}
    bindings = {binding.binding_id: binding for binding in source.credential_bindings}
    for consumer in source.consumer_bindings:
        if not consumer.enabled and not include_disabled:
            continue
        for specs in _consumer_access_specs(consumer, bindings):
            asset = assets.get(consumer.asset_id or "")
            resource_id = asset.asset_id if asset is not None else None
            _add_access_usage(
                groups,
                specs,
                _consumer_usage(consumer),
                resource_id=resource_id,
                asset_kind=asset.asset_kind if asset is not None else None,
            )
    return groups


def _consumer_access_specs(
    consumer: AccessConsumerBindingReadModel,
    bindings: Mapping[str, CredentialBindingReadModel],
) -> tuple[tuple[AccessReadinessCheckSpec, ...], ...]:
    specs: list[tuple[AccessReadinessCheckSpec, ...]] = []
    if consumer.credential_binding_id:
        binding = bindings.get(consumer.credential_binding_id)
        if binding is not None:
            specs.append(
                (
                    credential_binding_check_spec(
                        binding.source_ref,
                        allow_literal=not is_credential_binding(binding.source_ref),
                    ),
                ),
            )
    for requirement_set in consumer.requirement_sets:
        requirement_specs: list[AccessReadinessCheckSpec] = []
        for item in requirement_set:
            spec = _canonical_check_spec("requirement", str(item), False)
            if spec is not None:
                requirement_specs.append(spec)
        specs.append(tuple(requirement_specs))
    return tuple(item for item in specs if item)


def _consumer_usage(consumer: AccessConsumerBindingReadModel) -> dict[str, object]:
    metadata = sanitize_access_metadata(dict(consumer.metadata))
    usage: dict[str, object] = {
        "usage_type": consumer.consumer_kind,
        "usage_id": consumer.consumer_id,
        "consumer_module": consumer.consumer_module,
        "display_name": consumer.display_name or consumer.consumer_id,
        "enabled": consumer.enabled,
    }
    usage.update(metadata)
    if consumer.credential_binding_id:
        usage["credential_binding_id"] = consumer.credential_binding_id
    if consumer.requirement_sets:
        usage["access_requirement_sets"] = [
            list(items) for items in consumer.requirement_sets
        ]
        if len(consumer.requirement_sets) == 1:
            usage["access_requirement_set"] = list(consumer.requirement_sets[0])
    return usage


def _add_access_usage(
    groups: dict[tuple[AccessReadinessCheckSpec, ...], dict[str, object]],
    check_specs: tuple[AccessReadinessCheckSpec, ...],
    usage: dict[str, object],
    *,
    resource_id: str | None = None,
    display_name: str | None = None,
    asset_kind: str | None = None,
) -> None:
    key = _access_requirement_key(check_specs)
    if not key:
        return
    group = groups.setdefault(key, {"check_specs": key, "usages": []})
    if resource_id and "resource_id" not in group:
        group["resource_id"] = resource_id
    if display_name and "display_name" not in group:
        group["display_name"] = display_name
    if asset_kind and "asset_kind" not in group:
        group["asset_kind"] = asset_kind
    usages = group["usages"]
    if isinstance(usages, list):
        usages.append(dict(usage))


def _access_requirement_key(
    check_specs: tuple[AccessReadinessCheckSpec, ...],
) -> tuple[AccessReadinessCheckSpec, ...]:
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
) -> AccessReadinessCheckSpec | None:
    normalized = raw.strip()
    if not normalized:
        return None
    if target_type == "credential_binding":
        return credential_binding_check_spec(
            normalized,
            allow_literal=allow_literal,
        )

    binding = credential_binding_for_requirement(normalized)
    if binding is not None:
        return credential_binding_check_spec(binding, allow_literal=False)
    return ("requirement", normalized, False)


def _access_requirement_sort_key(group: Mapping[str, object]) -> tuple[str, str]:
    specs = tuple(group["check_specs"])
    display_name = str(group.get("display_name") or _access_requirement_display_name(specs))
    resource_id = str(group.get("resource_id") or _access_requirement_id(specs))
    return (display_name.lower(), resource_id)


def _access_requirement_display_name(specs: tuple[AccessReadinessCheckSpec, ...]) -> str:
    labels = [access_check_label(target_type, raw) for target_type, raw, _ in specs]
    if len(labels) == 1:
        return labels[0]
    return " + ".join(labels)


def _access_requirement_id(specs: tuple[AccessReadinessCheckSpec, ...]) -> str:
    raw = "|".join(
        f"{target_type}:{allow_literal}:{requirement}"
        for target_type, requirement, allow_literal in specs
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    prefix = _slugify(
        "+".join(
            access_check_label(target_type, requirement)
            for target_type, requirement, _ in specs
        ),
    )
    return f"access_requirement:{prefix}:{digest}"


def _access_requirement_metadata(
    specs: tuple[AccessReadinessCheckSpec, ...],
    group: Mapping[str, object],
) -> dict[str, object]:
    usages = _access_usages(group)
    enabled_count = sum(1 for usage in usages if bool(usage.get("enabled")))
    disabled_count = len(usages) - enabled_count
    metadata: dict[str, object] = {
        "asset_kind": str(group.get("asset_kind") or _access_requirement_asset_kind(specs)),
        "requirements": [raw for _, raw, _ in specs],
        "check_types": [target_type for target_type, _, _ in specs],
        "labels": [
            access_check_label(target_type, raw)
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


def _access_requirement_asset_kind(specs: tuple[AccessReadinessCheckSpec, ...]) -> str:
    if len(specs) != 1:
        return "credential_set"
    target_type, raw, _ = specs[0]
    if target_type == "credential_binding":
        return credential_asset_kind(raw)
    return "access_requirement"


def _access_usages(group: Mapping[str, object]) -> list[dict[str, object]]:
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
            values.add(
                masked_inventory_requirement(binding.strip(), allow_literal=False),
            )
        for field in (
            "access_requirement_set",
            "access_requirement_sets",
            "access_requirements",
        ):
            raw_values = usage.get(field)
            if not isinstance(raw_values, (list, tuple)):
                continue
            for raw_value in raw_values:
                if isinstance(raw_value, str) and raw_value.strip():
                    values.add(
                        masked_inventory_requirement(
                            raw_value.strip(),
                            allow_literal=False,
                        ),
                    )
                if isinstance(raw_value, (list, tuple)):
                    for nested_value in raw_value:
                        if isinstance(nested_value, str) and nested_value.strip():
                            values.add(
                                masked_inventory_requirement(
                                    nested_value.strip(),
                                    allow_literal=False,
                                ),
                            )
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
        "metadata": dict(sanitize_access_metadata(metadata)),
    }


def _requirement_set_payload(
    checks: tuple[dict[str, object], ...],
) -> dict[str, object]:
    return {
        "ready": all(bool(check.get("ready")) for check in checks),
        "checks": [_safe_check_payload(check) for check in checks],
    }


def _safe_check_payload(check: Mapping[str, object]) -> dict[str, object]:
    payload = dict(sanitize_access_metadata(check))
    raw_requirement = payload.get("requirement")
    target_type = str(payload.get("target_type") or "")
    allow_literal = bool(payload.get("allow_literal"))
    if isinstance(raw_requirement, str):
        if target_type == "credential_binding":
            payload["requirement"] = masked_inventory_requirement(
                raw_requirement,
                allow_literal=allow_literal,
            )
        else:
            binding = credential_binding_for_requirement(raw_requirement)
            if binding is not None:
                payload["requirement"] = masked_inventory_requirement(
                    binding,
                    allow_literal=False,
                )
    return payload
