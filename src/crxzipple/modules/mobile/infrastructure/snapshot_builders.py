from __future__ import annotations

from xml.etree import ElementTree as ET

from crxzipple.modules.mobile.domain import MobileStoredRef
from crxzipple.modules.ocr.domain import OcrPoint, OcrResult

from .ui_node_resolution import (
    is_interactive_node,
    is_truthy,
    label_for_node,
    parse_bounds,
)
from .vision_layout import VisionLayoutCandidate


def snapshot_from_source(
    *,
    source: str,
    generation: int,
) -> tuple[str, tuple[MobileStoredRef, ...], str, int]:
    root = ET.fromstring(source)
    lines: list[str] = []
    refs: list[MobileStoredRef] = []
    text_lines: list[str] = []
    node_count = 0

    def walk(node: ET.Element, depth: int, xpath: str) -> None:
        nonlocal node_count
        node_count += 1
        label = label_for_node(node)
        class_name = (node.attrib.get("class") or node.tag or "").strip()
        bounds = parse_bounds(node.attrib.get("bounds"))
        interactive = is_interactive_node(node)
        ref_label: str | None = None
        if interactive:
            ref_label = f"g{generation}-m{len(refs) + 1}"
            refs.append(
                MobileStoredRef(
                    ref=ref_label,
                    generation=generation,
                    source="ui_tree",
                    text=node.attrib.get("text"),
                    content_desc=node.attrib.get("content-desc"),
                    resource_id=node.attrib.get("resource-id"),
                    class_name=class_name,
                    xpath=xpath,
                    bounds=bounds,
                    clickable=is_truthy(node.attrib.get("clickable")),
                    focusable=is_truthy(node.attrib.get("focusable")),
                    focused=is_truthy(node.attrib.get("focused")),
                    enabled=not ((node.attrib.get("enabled") or "").strip().lower() == "false"),
                ),
            )
        suffix = f" [ref={ref_label}]" if ref_label is not None else ""
        lines.append(f"{'  ' * depth}- {class_name or 'node'} \"{label}\"{suffix}")
        label_text = label.strip()
        if label_text and label_text not in text_lines:
            text_lines.append(label_text)
        sibling_counts: dict[str, int] = {}
        for child in list(node):
            child_tag = child.tag
            sibling_counts[child_tag] = sibling_counts.get(child_tag, 0) + 1
            child_xpath = f"{xpath}/{child_tag}[{sibling_counts[child_tag]}]"
            walk(child, depth + 1, child_xpath)

    walk(root, 0, f"/{root.tag}[1]")
    return "\n".join(lines), tuple(refs), "\n".join(text_lines[:200]), node_count


def ui_tree_looks_low_quality(
    *,
    refs: tuple[MobileStoredRef, ...],
    text_excerpt: str,
    node_count: int,
    current_package: str | None,
) -> bool:
    if refs:
        return False
    meaningful_lines = _meaningful_snapshot_lines(text_excerpt)
    if node_count <= 3:
        return True
    if not meaningful_lines:
        return True
    if (current_package or "").startswith("com.tencent.mm") and len(meaningful_lines) <= 2:
        return True
    return False


def snapshot_from_ocr_result(
    *,
    result: OcrResult,
    generation: int,
    vision_candidates: tuple[VisionLayoutCandidate, ...] = (),
) -> tuple[str, tuple[MobileStoredRef, ...], str, int]:
    ordered_blocks = tuple(
        sorted(
            (
                (
                    block.text.strip(),
                    _bounds_from_ocr_polygon(block.polygon),
                    block.confidence,
                )
                for block in result.blocks
                if block.text.strip()
            ),
            key=lambda item: (
                item[1][1] if item[1] is not None else 0,
                item[1][0] if item[1] is not None else 0,
            ),
        ),
    )
    rows = _group_ocr_rows(tuple((text, bounds) for text, bounds, _ in ordered_blocks))
    refs: list[MobileStoredRef] = []
    lines = ["- ocr.page"]
    text_lines: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        lines.append(f"  - ocr.row #{row_index}")
        for text, bounds in row:
            ref_label: str | None = None
            if bounds is not None:
                ref_label = f"g{generation}-m{len(refs) + 1}"
                refs.append(
                    MobileStoredRef(
                        ref=ref_label,
                        generation=generation,
                        source="ocr",
                        text=text,
                        class_name="ocr.block",
                        bounds=bounds,
                        clickable=True,
                        focusable=False,
                        focused=False,
                        enabled=True,
                    ),
                )
            suffix = f" [ref={ref_label}]" if ref_label is not None else ""
            lines.append(f'    - ocr.block "{text}"{suffix}')
            if text not in text_lines:
                text_lines.append(text)
    vision_rows = _group_ocr_rows(
        tuple(
            (
                (candidate.label or candidate.kind).strip(),
                candidate.bounds,
            )
            for candidate in vision_candidates
        ),
    )
    if vision_rows:
        lines.append("  - vision.layout")
    for row_index, row in enumerate(vision_rows, start=1):
        lines.append(f"    - vision.row #{row_index}")
        for label, bounds in row:
            matched_candidate = next(
                (
                    candidate
                    for candidate in vision_candidates
                    if candidate.bounds == bounds and (candidate.label or candidate.kind).strip() == label
                ),
                None,
            )
            if matched_candidate is None:
                continue
            ref_label = f"g{generation}-m{len(refs) + 1}"
            refs.append(
                MobileStoredRef(
                    ref=ref_label,
                    generation=generation,
                    source="vision",
                    text=matched_candidate.label,
                    class_name=matched_candidate.kind,
                    bounds=matched_candidate.bounds,
                    clickable=True,
                    focusable=matched_candidate.kind == "vision.input",
                    focused=False,
                    enabled=True,
                ),
            )
            lines.append(
                f'      - {matched_candidate.kind} "{(matched_candidate.label or matched_candidate.kind)}" [ref={ref_label}]',
            )
            label_text = (matched_candidate.label or "").strip()
            if label_text and label_text not in text_lines:
                text_lines.append(label_text)
    node_count = (
        1
        + len(rows)
        + len(ordered_blocks)
        + (1 if vision_rows else 0)
        + len(vision_rows)
        + len(vision_candidates)
    )
    return "\n".join(lines), tuple(refs), "\n".join(text_lines[:200]), node_count


def _meaningful_snapshot_lines(text_excerpt: str) -> tuple[str, ...]:
    meaningful: list[str] = []
    for raw_line in text_excerpt.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered in {"hierarchy", "node"}:
            continue
        if lowered.startswith("android.widget.") or lowered.startswith("android.view."):
            continue
        if ":id/" in lowered:
            continue
        meaningful.append(line)
    return tuple(meaningful)


def _bounds_from_ocr_polygon(
    polygon: tuple[OcrPoint, ...],
) -> tuple[int, int, int, int] | None:
    if not polygon:
        return None
    xs = [int(round(point.x)) for point in polygon]
    ys = [int(round(point.y)) for point in polygon]
    if not xs or not ys:
        return None
    left = min(xs)
    right = max(xs)
    top = min(ys)
    bottom = max(ys)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _group_ocr_rows(
    blocks: tuple[tuple[str, tuple[int, int, int, int] | None], ...],
) -> tuple[tuple[tuple[str, tuple[int, int, int, int] | None], ...], ...]:
    if not blocks:
        return ()
    heights = [
        bounds[3] - bounds[1]
        for _, bounds in blocks
        if bounds is not None and bounds[3] > bounds[1]
    ]
    threshold = 40
    if heights:
        sorted_heights = sorted(heights)
        median_height = sorted_heights[len(sorted_heights) // 2]
        threshold = max(24, int(median_height * 0.8))
    rows: list[list[tuple[str, tuple[int, int, int, int] | None]]] = []
    row_tops: list[int] = []
    for item in blocks:
        _, bounds = item
        top = bounds[1] if bounds is not None else (row_tops[-1] if row_tops else 0)
        if rows and abs(top - row_tops[-1]) <= threshold:
            rows[-1].append(item)
            row_tops[-1] = min(row_tops[-1], top)
            continue
        rows.append([item])
        row_tops.append(top)
    normalized_rows: list[tuple[tuple[str, tuple[int, int, int, int] | None], ...]] = []
    for row in rows:
        normalized_rows.append(
            tuple(
                sorted(
                    row,
                    key=lambda item: item[1][0] if item[1] is not None else 0,
                ),
            ),
        )
    return tuple(normalized_rows)
