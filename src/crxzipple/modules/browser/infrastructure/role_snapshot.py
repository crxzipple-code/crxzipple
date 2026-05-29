from __future__ import annotations

from dataclasses import dataclass
import re


_INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "checkbox",
        "combobox",
        "gridcell",
        "link",
        "listbox",
        "menuitem",
        "option",
        "radio",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "tab",
        "textbox",
        "treeitem",
    }
)
_CONTENT_ROLES = frozenset(
    {
        "article",
        "cell",
        "columnheader",
        "gridcell",
        "heading",
        "listitem",
        "main",
        "navigation",
        "region",
        "rowheader",
    }
)
_STRUCTURAL_ROLES = frozenset(
    {
        "application",
        "directory",
        "document",
        "generic",
        "grid",
        "group",
        "ignored",
        "list",
        "menu",
        "menubar",
        "none",
        "presentation",
        "row",
        "rowgroup",
        "table",
        "tablist",
        "toolbar",
        "tree",
        "treegrid",
    }
)
_COMPACT_KEEP_UNNAMED_ROLES = frozenset(
    {
        "checkbox",
        "combobox",
        "listbox",
        "radio",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "textbox",
    }
)
_ROLE_LINE_RE = re.compile(r'^(\s*-\s*)([\w-]+)(?:\s+"([^"]*)")?(?::)?(.*)$')


@dataclass(frozen=True, slots=True)
class InteractiveRoleItem:
    role: str
    name: str | None = None
    nth: int | None = None


@dataclass(frozen=True, slots=True)
class RoleSnapshotRef:
    role: str
    name: str | None = None
    nth: int | None = None


@dataclass(frozen=True, slots=True)
class RoleSnapshot:
    snapshot: str
    refs: tuple[RoleSnapshotRef, ...]


@dataclass(frozen=True, slots=True)
class _ParsedRoleLine:
    depth: int
    prefix: str
    role_raw: str
    role: str
    name: str | None
    suffix: str


def build_interactive_role_items(
    aria_snapshot: str,
    *,
    max_depth: int | None = None,
    compact: bool = False,
) -> tuple[InteractiveRoleItem, ...]:
    raw_items: list[tuple[str, str | None]] = []
    for line in str(aria_snapshot or "").splitlines():
        parsed = _parse_role_line(line)
        if parsed is None:
            continue
        if max_depth is not None and parsed.depth > max_depth:
            continue
        if parsed.role not in _INTERACTIVE_ROLES:
            continue
        if compact and parsed.name is None and parsed.role not in _COMPACT_KEEP_UNNAMED_ROLES:
            continue
        raw_items.append((parsed.role, parsed.name))

    counts: dict[tuple[str, str | None], int] = {}
    for role, name in raw_items:
        key = (role, name)
        counts[key] = counts.get(key, 0) + 1

    seen: dict[tuple[str, str | None], int] = {}
    resolved: list[InteractiveRoleItem] = []
    for role, name in raw_items:
        key = (role, name)
        index = seen.get(key, 0)
        seen[key] = index + 1
        nth = index if counts.get(key, 0) > 1 else None
        resolved.append(
            InteractiveRoleItem(
                role=role,
                name=name,
                nth=nth,
            )
        )
    return tuple(resolved)


def build_role_snapshot(
    aria_snapshot: str,
    *,
    compact: bool = False,
    max_depth: int | None = None,
    interactive_only: bool = False,
    max_refs: int | None = None,
) -> RoleSnapshot:
    lines = str(aria_snapshot or "").splitlines()
    refs_by_index: dict[int, RoleSnapshotRef] = {}
    refs_by_key: dict[tuple[str, str | None], list[int]] = {}
    line_index_by_ref: dict[int, int] = {}
    result: list[str] = []

    for line in lines:
        parsed = _parse_role_line(line)
        if parsed is None:
            if not interactive_only and line.strip():
                result.append(line)
            continue
        if max_depth is not None and parsed.depth > max_depth:
            continue

        is_interactive = parsed.role in _INTERACTIVE_ROLES
        is_content = parsed.role in _CONTENT_ROLES
        is_structural = parsed.role in _STRUCTURAL_ROLES

        if interactive_only and not is_interactive:
            continue
        if (
            compact
            and is_interactive
            and parsed.name is None
            and parsed.role not in _COMPACT_KEEP_UNNAMED_ROLES
        ):
            continue
        if compact and is_structural and parsed.name is None:
            continue

        should_have_ref = is_interactive or (is_content and parsed.name is not None)
        if not should_have_ref:
            result.append(_format_role_line(parsed))
            continue
        if max_refs is not None and len(refs_by_index) >= max_refs:
            continue

        ref_index = len(refs_by_index) + 1
        refs_by_key.setdefault((parsed.role, parsed.name), []).append(ref_index)
        refs_by_index[ref_index] = RoleSnapshotRef(
            role=parsed.role,
            name=parsed.name,
            nth=None,
        )
        line_index_by_ref[ref_index] = len(result)
        result.append(_format_role_line(parsed, ref_index=ref_index))

    finalized_refs = _finalize_role_refs(refs_by_index=refs_by_index, refs_by_key=refs_by_key)
    finalized_lines = _apply_nth_annotations(
        lines=result,
        refs=finalized_refs,
        line_index_by_ref=line_index_by_ref,
    )
    snapshot = "\n".join(finalized_lines).strip() or (
        "(no interactive elements)" if interactive_only else "(empty)"
    )
    return RoleSnapshot(snapshot=snapshot, refs=tuple(finalized_refs))


def describe_role_locator(
    *,
    role: str,
    name: str | None,
    nth: int | None,
) -> str:
    description = f"role={role}"
    if name is not None:
        description += f'[name="{name}"]'
    if nth is not None:
        description += f"[nth={nth}]"
    return description


def _parse_role_line(line: str) -> _ParsedRoleLine | None:
    match = _ROLE_LINE_RE.match(line)
    if match is None:
        return None
    prefix, role_raw, name, suffix = match.groups()
    if role_raw.startswith("/"):
        return None
    depth = max(0, (len(prefix) - 2) // 2)
    role = role_raw.strip().lower()
    resolved_name = name.strip() if isinstance(name, str) and name.strip() else None
    return _ParsedRoleLine(
        depth=depth,
        prefix=prefix,
        role_raw=role_raw,
        role=role,
        name=resolved_name,
        suffix=suffix or "",
    )


def _format_role_line(parsed: _ParsedRoleLine, *, ref_index: int | None = None) -> str:
    line = f"{parsed.prefix}{parsed.role_raw}"
    if parsed.name is not None:
        line += f' "{parsed.name}"'
    if ref_index is not None:
        line += f" [ref=r{ref_index}]"
    if parsed.suffix:
        line += parsed.suffix
    return line


def _finalize_role_refs(
    *,
    refs_by_index: dict[int, RoleSnapshotRef],
    refs_by_key: dict[tuple[str, str | None], list[int]],
) -> list[RoleSnapshotRef]:
    finalized = dict(refs_by_index)
    for indexes in refs_by_key.values():
        if len(indexes) <= 1:
            continue
        for nth, index in enumerate(indexes):
            current = finalized[index]
            finalized[index] = RoleSnapshotRef(
                role=current.role,
                name=current.name,
                nth=nth,
            )
    return [finalized[index] for index in sorted(finalized)]


def _apply_nth_annotations(
    *,
    lines: list[str],
    refs: list[RoleSnapshotRef],
    line_index_by_ref: dict[int, int],
) -> list[str]:
    if not refs:
        return lines
    annotated = list(lines)
    for index, ref in enumerate(refs, start=1):
        if ref.nth is None:
            continue
        line_index = line_index_by_ref.get(index)
        if line_index is None:
            continue
        annotated[line_index] = annotated[line_index] + f" [nth={ref.nth}]"
    return annotated
