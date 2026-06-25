from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from crxzipple.modules.mobile.domain import MobileValidationError

_BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass(frozen=True, slots=True)
class ResolvedNode:
    text: str | None
    content_desc: str | None
    resource_id: str | None
    class_name: str | None
    xpath: str | None
    bounds: tuple[int, int, int, int] | None
    clickable: bool
    focusable: bool
    focused: bool
    enabled: bool


def parse_bounds(raw: str | None) -> tuple[int, int, int, int] | None:
    if not raw:
        return None
    match = _BOUNDS_PATTERN.fullmatch(raw.strip())
    if match is None:
        return None
    left, top, right, bottom = (int(part) for part in match.groups())
    return (left, top, right, bottom)


def bounds_center(bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = bounds
    return ((left + right) // 2, (top + bottom) // 2)


def is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def label_for_node(node: ET.Element) -> str:
    for key in ("text", "content-desc", "resource-id"):
        raw = (node.attrib.get(key) or "").strip()
        if raw:
            return raw
    class_name = (node.attrib.get("class") or node.tag or "").strip()
    return class_name or "node"


def is_interactive_node(node: ET.Element) -> bool:
    class_name = (node.attrib.get("class") or "").strip()
    return (
        is_truthy(node.attrib.get("clickable"))
        or is_truthy(node.attrib.get("focusable"))
        or class_name.endswith("EditText")
        or class_name.endswith("Button")
        or class_name.endswith("CheckBox")
        or class_name.endswith("Switch")
    )


def find_nodes_by_selector(source: str, selector: str) -> tuple[ResolvedNode, ...]:
    root = ET.fromstring(source)
    items = _iter_nodes(root)
    using, value = _parse_selector(selector)
    if using == "id":
        return tuple(
            _resolved_node(node, xpath)
            for node, xpath in items
            if (node.attrib.get("resource-id") or "").strip() == value
        )
    if using == "accessibility id":
        return tuple(
            _resolved_node(node, xpath)
            for node, xpath in items
            if (node.attrib.get("content-desc") or "").strip() == value
        )
    if using == "text":
        return tuple(
            _resolved_node(node, xpath)
            for node, xpath in items
            if (node.attrib.get("text") or "").strip() == value
        )
    if using == "xpath":
        try:
            matched = root.findall(_coerce_xpath_selector(value))
        except SyntaxError as exc:
            raise MobileValidationError(f"Unsupported xpath selector '{selector}'.") from exc
        xpath_lookup = {id(node): xpath for node, xpath in items}
        return tuple(
            _resolved_node(node, xpath_lookup.get(id(node), ""))
            for node in matched
            if isinstance(node, ET.Element)
        )
    raise MobileValidationError(f"Unsupported mobile selector strategy '{using}'.")


def resolved_nodes_from_source(source: str) -> tuple[ResolvedNode, ...]:
    root = ET.fromstring(source)
    return tuple(_resolved_node(node, xpath) for node, xpath in _iter_nodes(root))


def matches_target(candidate: ResolvedNode, target: ResolvedNode) -> bool:
    if target.resource_id and candidate.resource_id == target.resource_id:
        return True
    if target.xpath and candidate.xpath == target.xpath:
        return True
    if (
        target.bounds is not None
        and candidate.bounds == target.bounds
        and target.class_name
        and candidate.class_name == target.class_name
    ):
        return True
    return False


def _parse_selector(selector: str) -> tuple[str, str]:
    normalized = selector.strip()
    if normalized.startswith("xpath="):
        return "xpath", normalized[6:]
    if normalized.startswith("id="):
        return "id", normalized[3:]
    if normalized.startswith("accessibility_id="):
        return "accessibility id", normalized[len("accessibility_id=") :]
    if normalized.startswith("text="):
        return "text", normalized[5:]
    if normalized.startswith("//"):
        return "xpath", normalized
    return "xpath", normalized


def _iter_nodes(root: ET.Element) -> tuple[tuple[ET.Element, str], ...]:
    items: list[tuple[ET.Element, str]] = []

    def walk(node: ET.Element, xpath: str) -> None:
        items.append((node, xpath))
        sibling_counts: dict[str, int] = {}
        for child in list(node):
            child_tag = child.tag
            sibling_counts[child_tag] = sibling_counts.get(child_tag, 0) + 1
            child_xpath = f"{xpath}/{child_tag}[{sibling_counts[child_tag]}]"
            walk(child, child_xpath)

    walk(root, f"/{root.tag}[1]")
    return tuple(items)


def _resolved_node(node: ET.Element, xpath: str) -> ResolvedNode:
    class_name = (node.attrib.get("class") or node.tag or "").strip() or None
    return ResolvedNode(
        text=(node.attrib.get("text") or None),
        content_desc=(node.attrib.get("content-desc") or None),
        resource_id=(node.attrib.get("resource-id") or None),
        class_name=class_name,
        xpath=xpath,
        bounds=parse_bounds(node.attrib.get("bounds")),
        clickable=is_truthy(node.attrib.get("clickable")),
        focusable=is_truthy(node.attrib.get("focusable")),
        focused=is_truthy(node.attrib.get("focused")),
        enabled=not ((node.attrib.get("enabled") or "").strip().lower() == "false"),
    )


def _coerce_xpath_selector(value: str) -> str:
    selector = value.strip()
    if selector.startswith("//"):
        return f".{selector}"
    return selector
