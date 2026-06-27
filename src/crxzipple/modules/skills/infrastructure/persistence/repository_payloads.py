from __future__ import annotations

from crxzipple.modules.skills.domain import SkillRequirements


def requirements_from_payload(payload: dict[str, object] | None) -> SkillRequirements:
    raw = dict(payload or {})
    return SkillRequirements(
        required_tools=tuple_of_text(raw.get("required_tools")),
        optional_tools=tuple_of_text(raw.get("optional_tools")),
        suggested_tools=tuple_of_text(raw.get("suggested_tools")),
        required_effects=tuple_of_text(raw.get("required_effects")),
        surfaces=tuple_of_text(raw.get("surfaces")),
        supported_platforms=tuple_of_text(raw.get("supported_platforms")),
        required_access=tuple_of_text(raw.get("required_access")),
        setup_hints=tuple_of_text(raw.get("setup_hints")),
    )


def tuple_of_text(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item.strip())
