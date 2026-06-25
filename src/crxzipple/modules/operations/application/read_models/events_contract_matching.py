from __future__ import annotations

from typing import Any


def match_topic_contracts(registry: Any | None, topic: str) -> tuple[Any, ...]:
    if registry is None:
        return ()
    try:
        return tuple(registry.match_topic_contracts(topic))
    except Exception:
        return ()


def match_route_contracts(registry: Any | None, topic: str) -> tuple[Any, ...]:
    if registry is None:
        return ()
    try:
        return tuple(registry.match_route_contracts(topic))
    except Exception:
        return ()


def contract_status(
    *,
    observed: Any,
    definition: Any | None,
    contract_matches: tuple[Any, ...],
) -> str:
    name = _display(getattr(observed, "event_name", None)).lower()
    topic = _display(getattr(observed, "topic", None)).lower()
    if "dead_letter" in name or "dead-letter" in name or "dead_letter" in topic:
        return "dead_letter"
    has_definition = definition is not None
    has_contract = bool(contract_matches)
    if has_definition and has_contract:
        return "matched"
    if has_definition:
        return "definition_only"
    if has_contract:
        return "topic_contract_only"
    return "uncovered"


def contract_label(
    *,
    definition: Any | None,
    contract_matches: tuple[Any, ...],
) -> str:
    ids = contract_ids(contract_matches)
    definition_id = _display(getattr(definition, "definition_id", None))
    if ids and definition_id != "-":
        return f"{definition_id} / {_join(ids)}"
    if definition_id != "-":
        return definition_id
    if ids:
        return _join(ids)
    return "-"


def contract_ids(matches: tuple[Any, ...]) -> tuple[str, ...]:
    ids = []
    for match in matches:
        contract = getattr(match, "contract", None)
        contract_id = _display(getattr(contract, "contract_id", None))
        if contract_id != "-":
            ids.append(contract_id)
    return tuple(ids)


def match_payload(match: Any) -> dict[str, Any]:
    to_payload = getattr(match, "to_payload", None)
    if callable(to_payload):
        try:
            return _as_dict(_jsonable(to_payload()))
        except Exception:
            return {}
    return {}


def contract_matches_topic(contract: Any, topic: str) -> bool:
    pattern = _display(getattr(contract, "topic_pattern", None))
    return pattern_matches(pattern, topic)


def pattern_matches(pattern: str, topic: str) -> bool:
    if not pattern or pattern == "-":
        return False
    pattern_parts = pattern.split(".")
    topic_parts = topic.split(".")
    if len(pattern_parts) != len(topic_parts):
        return False
    for left, right in zip(pattern_parts, topic_parts):
        if left.startswith("{") and left.endswith("}"):
            continue
        if left != right:
            return False
    return True


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _display(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, (tuple, list, set)):
        return _join(tuple(_display(item) for item in value))
    return str(value)


def _join(values: tuple[Any, ...] | list[Any]) -> str:
    rendered = [
        str(value).strip()
        for value in values
        if str(value).strip() and str(value).strip() != "-"
    ]
    return ", ".join(rendered) if rendered else "-"
