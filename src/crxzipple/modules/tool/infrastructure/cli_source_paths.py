from __future__ import annotations

from pathlib import Path

from crxzipple.modules.tool.domain.exceptions import ToolValidationError


def resolve_executable(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ToolValidationError("CLI executable cannot be empty.")
    if "/" in normalized:
        return str(Path(normalized).expanduser().resolve())
    return normalized


def resolve_directory(
    value: object,
    *,
    default: Path,
    field_name: str,
) -> Path:
    raw = _optional_text(value)
    path = Path(raw).expanduser() if raw is not None else default
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ToolValidationError(f"CLI source directory '{field_name}' does not exist.")
    return resolved


def ensure_path_in_roots(
    path: Path,
    *,
    allowed_roots: tuple[Path, ...],
    field_name: str,
) -> None:
    resolved = path.resolve()
    for root in allowed_roots:
        try:
            resolved.relative_to(root.resolve())
            return
        except ValueError:
            continue
    roots = ", ".join(str(root) for root in allowed_roots)
    raise ToolValidationError(
        f"CLI source {field_name} '{resolved}' is outside allowed roots: {roots}.",
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "ensure_path_in_roots",
    "resolve_directory",
    "resolve_executable",
]
