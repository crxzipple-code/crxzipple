from __future__ import annotations


_SURFACE_CANONICAL_ALIASES = {
    "chat": "interactive",
    "webchat": "interactive",
}


def normalize_skill_surface(value: str | None) -> str:
    normalized = value.strip().lower() if isinstance(value, str) else ""
    return _SURFACE_CANONICAL_ALIASES.get(normalized, normalized)


def skill_surface_matches(
    supported_surfaces: tuple[str, ...],
    requested_surface: str | None,
) -> bool:
    requested = normalize_skill_surface(requested_surface)
    if not requested:
        return True
    supported = {
        normalize_skill_surface(surface)
        for surface in supported_surfaces
        if isinstance(surface, str) and surface.strip()
    }
    return not supported or requested in supported
