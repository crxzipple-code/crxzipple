from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.tool.application.catalog_models import ToolFunctionStatus
from crxzipple.modules.tool.application.source_command_models import (
    ToolFunctionCommandResult,
)
from crxzipple.modules.tool.application.source_events import (
    function_event as _function_event,
)
from crxzipple.modules.tool.application.source_record_mapping import (
    function_entity_to_record as _function_entity_to_record,
)
from crxzipple.modules.tool.application.source_unit_of_work import (
    ToolSourceUnitOfWork,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError


class ToolFunctionCommandService:
    def __init__(self, uow_factory: Callable[[], ToolSourceUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def set_function_enabled(
        self,
        function_id: str,
        *,
        enabled: bool,
    ) -> ToolFunctionCommandResult:
        with self._uow_factory() as uow:
            function = uow.tool_functions.get(function_id)
            if function is None:
                raise ToolValidationError(
                    f"Tool function '{function_id}' does not exist.",
                )
            if function.status is ToolFunctionStatus.DELETED:
                raise ToolValidationError(
                    f"Tool function '{function_id}' is deleted.",
                )
            changed = function.enabled is not bool(enabled)
            if changed:
                function.enabled = bool(enabled)
                function.revision += 1
                function.updated_at = _utc_now()
                function.record_event(
                    _function_event(
                        (
                            "tool.function.enabled"
                            if function.enabled
                            else "tool.function.disabled"
                        ),
                        _function_entity_to_record(function),
                        observed_at=function.updated_at,
                        changed_fields=("enabled",),
                    ),
                )
                uow.tool_functions.upsert(function)
                uow.collect(function)
                uow.commit()
            return ToolFunctionCommandResult(
                function=_function_entity_to_record(function),
                changed=changed,
            )

    def update_function_policy(
        self,
        function_id: str,
        *,
        trust_policy: Mapping[str, Any],
        approval_policy: Mapping[str, Any],
        credential_binding_overrides: Mapping[str, str],
        required_effect_overrides: tuple[str, ...] | None,
    ) -> ToolFunctionCommandResult:
        with self._uow_factory() as uow:
            function = uow.tool_functions.get(function_id)
            if function is None:
                raise ToolValidationError(
                    f"Tool function '{function_id}' does not exist.",
                )
            if function.status is ToolFunctionStatus.DELETED:
                raise ToolValidationError(
                    f"Tool function '{function_id}' is deleted.",
                )
            current = _function_entity_to_record(function)
            updated = replace(
                current,
                trust_policy=trust_policy,
                approval_policy=approval_policy,
                credential_binding_overrides=credential_binding_overrides,
                required_effect_overrides=required_effect_overrides,
            )
            changed_fields = tuple(
                field_name
                for field_name, current_value, next_value in (
                    ("trust_policy", current.trust_policy, updated.trust_policy),
                    ("approval_policy", current.approval_policy, updated.approval_policy),
                    (
                        "credential_binding_overrides",
                        current.credential_binding_overrides,
                        updated.credential_binding_overrides,
                    ),
                    (
                        "required_effect_overrides",
                        current.required_effect_overrides,
                        updated.required_effect_overrides,
                    ),
                )
                if current_value != next_value
            )
            changed = bool(changed_fields)
            if changed:
                function.trust_policy = dict(updated.trust_policy)
                function.approval_policy = dict(updated.approval_policy)
                function.credential_binding_overrides = dict(
                    updated.credential_binding_overrides,
                )
                function.required_effect_overrides = (
                    tuple(updated.required_effect_overrides)
                    if updated.required_effect_overrides is not None
                    else None
                )
                function.revision += 1
                function.updated_at = _utc_now()
                function.record_event(
                    _function_event(
                        "tool.function.policy_updated",
                        _function_entity_to_record(function),
                        observed_at=function.updated_at,
                        changed_fields=changed_fields,
                    ),
                )
                uow.tool_functions.upsert(function)
                uow.collect(function)
                uow.commit()
            return ToolFunctionCommandResult(
                function=_function_entity_to_record(function),
                changed=changed,
            )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = ["ToolFunctionCommandService"]
