from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

from crxzipple.modules.tool.application.specifications import ToolParameter
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.cli_source_config_values import (
    argv_tuple,
    bool_value,
    mapping_tuple,
    optional_positive_int,
    optional_text,
    required_text,
    safe_tool_id,
    text_tuple,
)

PROMOTED_ARG_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True, slots=True)
class CliPromotedFunctionParameterConfig:
    name: str
    data_type: str = "string"
    description: str = ""
    required: bool = True

    def as_tool_parameter(self) -> ToolParameter:
        return ToolParameter(
            name=self.name,
            data_type=self.data_type,
            description=self.description,
            required=self.required,
        )


@dataclass(frozen=True, slots=True)
class CliPromotedFunctionConfig:
    function_id: str
    name: str
    description: str
    subcommand: str
    args: tuple[str, ...] = ()
    parameters: tuple[CliPromotedFunctionParameterConfig, ...] = ()
    initial_output_limit: int | None = None
    mutates_state: bool = False
    required_effect_ids: tuple[str, ...] = ()

    def render_args(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        rendered: list[str] = []
        for template in self.args:
            exact_match = PROMOTED_ARG_PATTERN.fullmatch(template)
            if exact_match is not None:
                name = exact_match.group(1)
                value = _promoted_argument_value(
                    arguments,
                    name,
                    parameters=self.parameters,
                    embedded=False,
                )
                if value is None:
                    continue
                if isinstance(value, list | tuple):
                    rendered.extend(_promoted_scalar_text(item, name) for item in value)
                    continue
                rendered.append(_promoted_scalar_text(value, name))
                continue

            names = PROMOTED_ARG_PATTERN.findall(template)
            if not names:
                rendered.append(template)
                continue
            value_by_name = {
                name: _promoted_argument_value(
                    arguments,
                    name,
                    parameters=self.parameters,
                    embedded=True,
                )
                for name in names
            }

            def replace(match: re.Match[str]) -> str:
                name = match.group(1)
                value = value_by_name[name]
                if isinstance(value, list | tuple):
                    raise ToolValidationError(
                        f"CLI promoted argument '{name}' cannot expand an array inside argv template.",
                    )
                return _promoted_scalar_text(value, name)

            rendered.append(PROMOTED_ARG_PATTERN.sub(replace, template))
        return tuple(rendered)

    def metadata_payload(self) -> dict[str, Any]:
        return {
            "id": self.function_id,
            "name": self.name,
            "description": self.description,
            "subcommand": self.subcommand,
            "args": self.args,
            "parameters": tuple(
                {
                    "name": parameter.name,
                    "data_type": parameter.data_type,
                    "description": parameter.description,
                    "required": parameter.required,
                }
                for parameter in self.parameters
            ),
            "initial_output_limit": self.initial_output_limit,
            "mutates_state": self.mutates_state,
            "required_effect_ids": self.required_effect_ids,
        }


def promoted_function_configs(
    value: object,
    *,
    source_id: str,
) -> tuple[CliPromotedFunctionConfig, ...]:
    configs: list[CliPromotedFunctionConfig] = []
    for index, item in enumerate(
        mapping_tuple(value, field_name=f"{source_id}.provider.promoted_functions"),
    ):
        function_id = _safe_promoted_id(
            required_text(
                item.get("id") or item.get("function_id"),
                field_name=f"{source_id}.provider.promoted_functions[{index}].id",
            ),
        )
        raw_args = item.get("args")
        if raw_args is None:
            raw_args = item.get("argv")
        args = argv_tuple(
            raw_args,
            field_name=f"{source_id}.provider.promoted_functions[{index}].args",
        )
        parameters = _promoted_parameter_configs(
            item.get("parameters"),
            args=args,
            field_name=f"{source_id}.provider.promoted_functions[{index}].parameters",
        )
        configs.append(
            CliPromotedFunctionConfig(
                function_id=function_id,
                name=required_text(
                    item.get("name"),
                    field_name=f"{source_id}.provider.promoted_functions[{index}].name",
                ),
                description=required_text(
                    item.get("description"),
                    field_name=(
                        f"{source_id}.provider.promoted_functions[{index}].description"
                    ),
                ),
                subcommand=required_text(
                    item.get("subcommand"),
                    field_name=(
                        f"{source_id}.provider.promoted_functions[{index}].subcommand"
                    ),
                ),
                args=args,
                parameters=parameters,
                initial_output_limit=optional_positive_int(
                    item.get("initial_output_limit"),
                ),
                mutates_state=bool_value(item.get("mutates_state"), default=False),
                required_effect_ids=text_tuple(item.get("required_effect_ids")),
            ),
        )
    _ensure_unique_promoted_functions(configs, source_id=source_id)
    return tuple(configs)


def _promoted_parameter_configs(
    value: object,
    *,
    args: tuple[str, ...],
    field_name: str,
) -> tuple[CliPromotedFunctionParameterConfig, ...]:
    explicit = mapping_tuple(value, field_name=field_name)
    if not explicit:
        return tuple(
            CliPromotedFunctionParameterConfig(name=name)
            for name in _promoted_placeholders(args)
        )
    parameters: list[CliPromotedFunctionParameterConfig] = []
    for index, item in enumerate(explicit):
        parameters.append(
            CliPromotedFunctionParameterConfig(
                name=_safe_parameter_name(
                    required_text(
                        item.get("name"),
                        field_name=f"{field_name}[{index}].name",
                    ),
                ),
                data_type=optional_text(item.get("data_type")) or "string",
                description=optional_text(item.get("description")) or "",
                required=bool_value(item.get("required"), default=True),
            ),
        )
    _ensure_unique_promoted_parameters(parameters, field_name=field_name)
    return tuple(parameters)


def _promoted_placeholders(args: tuple[str, ...]) -> tuple[str, ...]:
    names: list[str] = []
    for template in args:
        names.extend(PROMOTED_ARG_PATTERN.findall(template))
    return tuple(dict.fromkeys(names))


def _promoted_argument_value(
    arguments: Mapping[str, Any],
    name: str,
    *,
    parameters: tuple[CliPromotedFunctionParameterConfig, ...],
    embedded: bool,
) -> Any:
    parameter = next(
        (candidate for candidate in parameters if candidate.name == name),
        None,
    )
    required = parameter.required if parameter is not None else True
    value = arguments.get(name)
    if value is None or value == "":
        if required or embedded:
            raise ToolValidationError(
                f"CLI promoted function argument '{name}' is required.",
            )
        return None
    return value


def _promoted_scalar_text(value: object, name: str) -> str:
    if isinstance(value, dict):
        raise ToolValidationError(
            f"CLI promoted function argument '{name}' must be a scalar or array.",
        )
    text = str(value).strip()
    if not text:
        raise ToolValidationError(
            f"CLI promoted function argument '{name}' cannot be empty.",
        )
    return text


def _ensure_unique_promoted_functions(
    configs: list[CliPromotedFunctionConfig],
    *,
    source_id: str,
) -> None:
    ids = [config.function_id for config in configs]
    if len(ids) != len(set(ids)):
        raise ToolValidationError(
            f"Configured CLI source '{source_id}' has duplicate promoted function ids.",
        )


def _ensure_unique_promoted_parameters(
    parameters: list[CliPromotedFunctionParameterConfig],
    *,
    field_name: str,
) -> None:
    names = [parameter.name for parameter in parameters]
    if len(names) != len(set(names)):
        raise ToolValidationError(
            f"CLI source field '{field_name}' has duplicate parameter names.",
        )


def _safe_promoted_id(value: str) -> str:
    normalized = safe_tool_id(value)
    if not normalized:
        raise ToolValidationError("CLI promoted function id cannot be empty.")
    return normalized


def _safe_parameter_name(value: str) -> str:
    normalized = value.strip()
    if not PROMOTED_ARG_PATTERN.fullmatch(f"{{{normalized}}}"):
        raise ToolValidationError(
            f"CLI promoted parameter name '{value}' is invalid.",
        )
    return normalized
