from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserStoredRef,
    BrowserTab,
    BrowserValidationError,
)
from crxzipple.modules.browser.domain.value_objects import _normalize_optional_text

from .action_engine_locators import _active_overlay, _effective_root_selector
from .action_engine_payloads import _probe_timeout, _timeout_kwargs
from .action_engine_scripts import _INTERACTIVE_SNAPSHOT_EXPRESSION
from .action_engine_snapshots import (
    _combine_frame_snapshots,
    _dedupe_nested_snapshot_candidates,
    _interactive_role_snapshot_is_too_sparse,
    _interactive_snapshot_limit,
    _is_frame_detached_error,
    _is_low_value_interactive_name,
    _is_transient_page_context_error,
    _resolve_snapshot_format,
    _role_snapshot_stats,
    _snapshot_compact,
    _snapshot_depth,
    _snapshot_frame_selector,
    _snapshot_item_backend_node_id,
    _snapshot_item_bbox,
    _snapshot_item_confidence,
    _snapshot_item_disabled,
    _snapshot_item_evidence,
    _snapshot_item_is_low_value_boilerplate,
    _snapshot_item_priority,
    _snapshot_item_semantic_key,
    _snapshot_item_visible,
    _snapshot_mode,
    _snapshot_refs_mode,
    _snapshot_root_contexts,
    _snapshot_root_locator,
)
from .role_snapshot import build_role_snapshot


class BrowserSnapshotActionMixin:
    def _snapshot(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        command: BrowserPageActionCommand,
    ) -> dict[str, Any]:
        snapshot_format = _resolve_snapshot_format(command.payload)
        snapshot_mode = _snapshot_mode(command.payload, snapshot_format=snapshot_format)
        snapshot_compact = _snapshot_compact(command.payload, snapshot_format=snapshot_format)
        snapshot_depth = _snapshot_depth(command.payload, snapshot_format=snapshot_format)
        refs_mode = _snapshot_refs_mode(command.payload)
        frame_selector = _snapshot_frame_selector(command.payload)
        root_selector = _effective_root_selector(
            page=page,
            runtime_state=runtime_state,
            tab=tab,
            payload=command.payload,
            root_selector=command.target.selector,
        )
        ref_count = 0
        frame_count = 0
        generation = 0
        if snapshot_format == "html":
            value = page.content()
        elif snapshot_format == "text":
            value = page.locator("body").inner_text()
        elif snapshot_format == "title":
            value = page.title()
        elif snapshot_format == "url":
            value = page.url
        elif snapshot_format == "aria":
            value, frame_count = self._aria_snapshot(
                page=page,
                frame_selector=frame_selector,
                root_selector=root_selector,
            )
        elif snapshot_format == "role":
            value, ref_count, frame_count, generation = self._role_snapshot(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                snapshot_format=snapshot_format,
                compact=snapshot_compact,
                depth=snapshot_depth,
                frame_selector=frame_selector,
                root_selector=root_selector,
            )
        elif snapshot_format == "interactive":
            value, ref_count, frame_count, generation = self._interactive_snapshot(
                plan=plan,
                tab=tab,
                page=page,
                runtime_state=runtime_state,
                snapshot_format=snapshot_format,
                snapshot_mode=snapshot_mode,
                limit=command.payload.get("limit"),
                compact=snapshot_compact,
                depth=snapshot_depth,
                payload=command.payload,
                frame_selector=frame_selector,
                root_selector=root_selector,
            )
        else:
            raise BrowserValidationError(
                f"Unsupported snapshot format '{snapshot_format}'.",
            )
        return {
            "kind": "snapshot",
            "format": snapshot_format,
            "generation": generation,
            "value": value,
            "ref_count": ref_count,
            "frame_count": frame_count,
            "mode": snapshot_mode,
            "compact": snapshot_compact,
            "depth": snapshot_depth,
            "refs_mode": refs_mode,
            "frame_selector": frame_selector,
            "root_selector": root_selector,
            "active_overlay": _active_overlay(command.payload),
        }

    def _aria_snapshot(
        self,
        *,
        page,
        frame_selector: str | None,
        root_selector: str | None,
    ) -> tuple[dict[str, Any], int]:
        frames: list[dict[str, Any]] = []
        for frame, frame_path in _snapshot_root_contexts(
            page,
            frame_selector=frame_selector,
            root_selector=root_selector,
        ):
            snapshot = _snapshot_root_locator(
                frame,
                root_selector=root_selector,
            ).aria_snapshot(**_timeout_kwargs(_probe_timeout(None)))
            frames.append(
                {
                    "frame_path": list(frame_path),
                    "snapshot": str(snapshot or "(empty)"),
                }
            )
        return {
            "snapshot": _combine_frame_snapshots(frames),
            "frames": frames,
        }, len(frames)

    def _role_snapshot(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        snapshot_format: str,
        compact: bool,
        depth: int | None,
        frame_selector: str | None,
        root_selector: str | None,
    ) -> tuple[dict[str, Any], int, int, int]:
        generation = runtime_state.next_ref_generation(target_id=tab.target_id)
        stored_refs: list[BrowserStoredRef] = []
        frames: list[dict[str, Any]] = []
        for frame, frame_path in _snapshot_root_contexts(
            page,
            frame_selector=frame_selector,
            root_selector=root_selector,
        ):
            aria_snapshot = _snapshot_root_locator(
                frame,
                root_selector=root_selector,
            ).aria_snapshot(**_timeout_kwargs(_probe_timeout(None)))
            built = build_role_snapshot(
                str(aria_snapshot or ""),
                compact=compact,
                max_depth=depth,
            )
            frame_refs: list[dict[str, Any]] = []
            for ref in built.refs:
                stored = BrowserStoredRef(
                    ref=f"r{len(stored_refs) + 1}",
                    scope_selector=root_selector,
                    nth=ref.nth,
                    generation=generation,
                    snapshot_format=snapshot_format,
                    frame_path=frame_path,
                    label=ref.name,
                    role=ref.role,
                    text=ref.name,
                    tag=ref.role,
                )
                stored_refs.append(stored)
                frame_refs.append(
                    {
                        "ref": stored.ref,
                        "selector": stored.selector,
                        "scope_selector": stored.scope_selector,
                        "uid": stored.uid,
                        "nth": stored.nth,
                        "generation": stored.generation,
                        "frame_path": list(stored.frame_path),
                        "label": stored.label,
                        "role": stored.role,
                        "text": stored.text,
                        "tag": stored.tag,
                        "frame_id": stored.frame_id,
                        "backend_node_id": stored.backend_node_id,
                        "bbox": dict(stored.bbox) if stored.bbox is not None else None,
                        "evidence": list(stored.evidence),
                        "confidence": stored.confidence,
                        "format": snapshot_format,
                    }
                )
            frames.append(
                {
                    "frame_path": list(frame_path),
                    "snapshot": built.snapshot,
                    "refs": frame_refs,
                    "ref_count": len(frame_refs),
                }
            )
        refs_tuple = tuple(stored_refs)
        self.ref_store.save_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
            refs=refs_tuple,
        )
        combined_snapshot = _combine_frame_snapshots(frames)
        return {
            "snapshot": combined_snapshot,
            "frames": frames,
            "refs": [frame_ref for frame in frames for frame_ref in frame["refs"]],
            "stats": _role_snapshot_stats(snapshot=combined_snapshot, refs=refs_tuple),
        }, len(refs_tuple), len(frames), generation

    def _interactive_snapshot(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        snapshot_format: str,
        snapshot_mode: str | None,
        limit: Any,
        compact: bool,
        depth: int | None,
        payload: Mapping[str, Any],
        frame_selector: str | None,
        root_selector: str | None,
    ) -> tuple[dict[str, Any], int, int, int]:
        effective_limit = _interactive_snapshot_limit(payload, snapshot_format, limit)
        role_snapshot = self._interactive_role_snapshot(
            plan=plan,
            tab=tab,
            page=page,
            runtime_state=runtime_state,
            snapshot_format=snapshot_format,
            snapshot_mode=snapshot_mode,
            limit=effective_limit,
            compact=compact,
            depth=depth,
            frame_selector=frame_selector,
            root_selector=root_selector,
        )
        if role_snapshot is not None:
            return role_snapshot

        return self._dom_interactive_snapshot(
            plan=plan,
            tab=tab,
            page=page,
            runtime_state=runtime_state,
            snapshot_format=snapshot_format,
            snapshot_mode=snapshot_mode,
            limit=effective_limit,
            frame_selector=frame_selector,
            root_selector=root_selector,
        )

    def _interactive_role_snapshot(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        snapshot_format: str,
        snapshot_mode: str | None,
        limit: Any,
        compact: bool,
        depth: int | None,
        frame_selector: str | None,
        root_selector: str | None,
    ) -> tuple[dict[str, Any], int, int, int] | None:
        stored_refs: list[BrowserStoredRef] = []
        generation = runtime_state.next_ref_generation(target_id=tab.target_id)
        max_items = limit
        effective_compact = compact
        if snapshot_mode == "focused":
            effective_compact = True
        frames: list[dict[str, Any]] = []
        for frame, frame_path in _snapshot_root_contexts(
            page,
            frame_selector=frame_selector,
            root_selector=root_selector,
        ):
            try:
                aria_snapshot = _snapshot_root_locator(
                    frame,
                    root_selector=root_selector,
                ).aria_snapshot(
                    **_timeout_kwargs(_probe_timeout(None))
                )
            except Exception:  # noqa: BLE001
                return None
            remaining_refs = None
            if max_items is not None:
                remaining_refs = max(0, max_items - len(stored_refs))
                if remaining_refs == 0:
                    break
            built = build_role_snapshot(
                str(aria_snapshot or ""),
                compact=effective_compact,
                max_depth=depth,
                interactive_only=True,
                max_refs=remaining_refs,
            )
            candidate_refs = list(built.refs)
            if snapshot_mode != "wide":
                candidate_refs = [
                    ref
                    for ref in candidate_refs
                    if not (
                        ref.role == "link"
                        and _is_low_value_interactive_name(ref.name)
                    )
                ]
            frame_refs: list[BrowserStoredRef] = []
            for ref in candidate_refs:
                stored = BrowserStoredRef(
                    ref=f"r{len(stored_refs) + 1}",
                    scope_selector=root_selector,
                    nth=ref.nth,
                    generation=generation,
                    snapshot_format=snapshot_format,
                    frame_path=frame_path,
                    label=ref.name,
                    role=ref.role,
                    text=ref.name,
                    tag=ref.role,
                )
                stored_refs.append(stored)
                frame_refs.append(stored)
            if frame_refs:
                frames.append(
                    {
                        "frame_path": list(frame_path),
                        "snapshot": built.snapshot,
                        "refs": self._interactive_refs_payload(
                            refs=tuple(frame_refs),
                            snapshot_format=snapshot_format,
                        ),
                        "ref_count": len(frame_refs),
                    }
                )
            if max_items is not None and len(stored_refs) >= max_items:
                break

        if not stored_refs:
            return None
        if _interactive_role_snapshot_is_too_sparse(
            snapshot_mode=snapshot_mode,
            root_selector=root_selector,
            ref_count=len(stored_refs),
        ):
            return None
        refs_tuple = tuple(stored_refs)
        self.ref_store.save_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
            refs=refs_tuple,
        )
        combined_snapshot = _combine_frame_snapshots(frames)
        return {
            "snapshot": combined_snapshot,
            "frames": frames,
            "refs": self._interactive_refs_payload(
                refs=refs_tuple,
                snapshot_format=snapshot_format,
            ),
            "stats": _role_snapshot_stats(snapshot=combined_snapshot, refs=refs_tuple),
        }, len(refs_tuple), len(frames), generation

    def _interactive_ref_line(self, *, item: BrowserStoredRef, indent: int = 0) -> str:
        role = str(item.role or "generic").strip() or "generic"
        line = f"- {role}"
        name = _normalize_optional_text(item.label or item.text)
        if name is not None:
            line += f' "{name}"'
        line += f" [ref={item.ref}]"
        if item.nth is not None:
            line += f" [nth={item.nth}]"
        if item.confidence is not None:
            line += f" [confidence={item.confidence:.2f}]"
        if item.evidence:
            evidence = ",".join(item.evidence[:4])
            if len(item.evidence) > 4:
                evidence = f"{evidence},..."
            line += f" [evidence={evidence}]"
        return f'{"  " * indent}{line}'

    def _interactive_frame_snapshot(
        self,
        *,
        refs: tuple[BrowserStoredRef, ...],
        root_selector: str | None = None,
    ) -> str:
        if not refs:
            return "(no interactive elements)"
        grouped_refs: dict[str, list[BrowserStoredRef]] = {}
        scope_order: list[str] = []
        ungrouped_refs: list[BrowserStoredRef] = []
        for item in refs:
            scope_selector = _normalize_optional_text(item.scope_selector)
            if scope_selector is None:
                ungrouped_refs.append(item)
                continue
            if scope_selector not in grouped_refs:
                grouped_refs[scope_selector] = []
                scope_order.append(scope_selector)
            grouped_refs[scope_selector].append(item)

        lines: list[str] = []
        for item in ungrouped_refs:
            lines.append(self._interactive_ref_line(item=item))
        for scope_selector in scope_order:
            lines.append(f'- scope "{scope_selector}":')
            for item in grouped_refs[scope_selector]:
                lines.append(self._interactive_ref_line(item=item, indent=1))
        return "\n".join(lines)

    def _interactive_refs_payload(
        self,
        *,
        refs: tuple[BrowserStoredRef, ...],
        snapshot_format: str,
    ) -> list[dict[str, Any]]:
        return [
            {
                "ref": item.ref,
                "selector": item.selector,
                "scope_selector": item.scope_selector,
                "uid": item.uid,
                "nth": item.nth,
                "generation": item.generation,
                "frame_path": list(item.frame_path),
                "label": item.label,
                "role": item.role,
                "text": item.text,
                "tag": item.tag,
                "frame_id": item.frame_id,
                "backend_node_id": item.backend_node_id,
                "bbox": dict(item.bbox) if item.bbox is not None else None,
                "evidence": list(item.evidence),
                "confidence": item.confidence,
                "format": snapshot_format,
            }
            for item in refs
        ]

    def _dom_interactive_snapshot(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        snapshot_format: str,
        snapshot_mode: str | None,
        limit: Any,
        frame_selector: str | None,
        root_selector: str | None,
    ) -> tuple[dict[str, Any], int, int, int]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return self._dom_interactive_snapshot_once(
                    plan=plan,
                    tab=tab,
                    page=page,
                    runtime_state=runtime_state,
                    snapshot_format=snapshot_format,
                    snapshot_mode=snapshot_mode,
                    limit=limit,
                    frame_selector=frame_selector,
                    root_selector=root_selector,
                )
            except Exception as exc:  # noqa: BLE001
                if attempt == 0 and _is_frame_detached_error(exc):
                    last_error = exc
                    continue
                raise
        assert last_error is not None
        raise last_error

    def _enrich_snapshot_item_with_devtools(
        self,
        *,
        page,
        frame_path: tuple[int, ...],
        item: Mapping[str, Any],
    ) -> dict[str, Any]:
        enriched = dict(item)
        if frame_path:
            return enriched
        if self.devtools_adapter is None:
            return enriched
        if _snapshot_item_backend_node_id(enriched) is not None:
            return enriched
        bbox = _snapshot_item_bbox(enriched)
        if bbox is None:
            return enriched
        try:
            node = self.devtools_adapter.get_node_for_location(
                page,
                x=int(round(bbox["x"] + bbox["width"] / 2)),
                y=int(round(bbox["y"] + bbox["height"] / 2)),
            )
        except BrowserValidationError:
            return enriched
        backend_node_id = _snapshot_item_backend_node_id(
            {"backend_node_id": node.get("backendNodeId")},
        )
        if backend_node_id is None:
            return enriched
        enriched["backend_node_id"] = backend_node_id
        evidence = list(_snapshot_item_evidence(enriched))
        if "devtools-hit-test" not in evidence:
            evidence.append("devtools-hit-test")
        enriched["evidence"] = evidence
        confidence = _snapshot_item_confidence(enriched)
        if confidence is not None:
            enriched["confidence"] = min(round(confidence + 0.05, 2), 0.99)
        return enriched

    def _dom_interactive_snapshot_once(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page,
        runtime_state: BrowserProfileRuntimeState,
        snapshot_format: str,
        snapshot_mode: str | None,
        limit: Any,
        frame_selector: str | None,
        root_selector: str | None,
    ) -> tuple[dict[str, Any], int, int, int]:
        snapshot_candidates: list[tuple[tuple[int, ...], dict[str, Any]]] = []
        generation = runtime_state.next_ref_generation(target_id=tab.target_id)
        max_items = limit
        for frame, frame_path in _snapshot_root_contexts(
            page,
            frame_selector=frame_selector,
            root_selector=root_selector,
        ):
            try:
                raw_items = frame.evaluate(
                    _INTERACTIVE_SNAPSHOT_EXPRESSION,
                    root_selector,
                )
            except Exception as exc:  # noqa: BLE001
                if frame_path and _is_transient_page_context_error(exc):
                    continue
                raise
            if not isinstance(raw_items, list):
                raise BrowserValidationError(
                    "Interactive snapshot did not return a list of elements.",
                )
            candidate_items = [item for item in raw_items if isinstance(item, dict)]
            if snapshot_mode != "wide":
                candidate_items = [
                    item
                    for item in candidate_items
                    if (
                        _snapshot_item_visible(item)
                        and not _snapshot_item_disabled(item)
                        and not _snapshot_item_is_low_value_boilerplate(item)
                    )
                ]
                candidate_items = [
                    item
                    for _index, item in sorted(
                        enumerate(candidate_items),
                        key=lambda entry: (-_snapshot_item_priority(entry[1]), entry[0]),
                    )
                ]
            for item in candidate_items:
                if not isinstance(item, dict):
                    continue
                selector = item.get("selector")
                if not isinstance(selector, str) or not selector.strip():
                    continue
                snapshot_candidates.append(
                    (
                        frame_path,
                        self._enrich_snapshot_item_with_devtools(
                            page=page,
                            frame_path=frame_path,
                            item=item,
                        ),
                    )
                )
                if max_items is not None and len(snapshot_candidates) >= max_items:
                    break
            if max_items is not None and len(snapshot_candidates) >= max_items:
                break

        semantic_counts: dict[tuple[str, str], int] = {}
        snapshot_candidates = _dedupe_nested_snapshot_candidates(snapshot_candidates)
        for _frame_path, item in snapshot_candidates:
            semantic_key = _snapshot_item_semantic_key(item)
            if semantic_key is None:
                continue
            semantic_counts[semantic_key] = semantic_counts.get(semantic_key, 0) + 1

        semantic_seen: dict[tuple[str, str], int] = {}
        resolved_items: list[BrowserStoredRef] = []
        for frame_path, item in snapshot_candidates:
            semantic_key = _snapshot_item_semantic_key(item)
            nth: int | None = None
            if semantic_key is not None and semantic_counts.get(semantic_key, 0) > 1:
                nth = semantic_seen.get(semantic_key, 0)
                semantic_seen[semantic_key] = nth + 1
            resolved_items.append(
                BrowserStoredRef(
                    ref=f"r{len(resolved_items) + 1}",
                    selector=str(item["selector"]),
                    scope_selector=(
                        str(item["scope_selector"]).strip()
                        if item.get("scope_selector") is not None
                        and str(item["scope_selector"]).strip()
                        else root_selector
                    ),
                    nth=nth,
                    generation=generation,
                    snapshot_format=snapshot_format,
                    frame_path=frame_path,
                    label=(
                        str(item["label"]) if item.get("label") is not None else None
                    ),
                    role=(
                        str(item["role"]) if item.get("role") is not None else None
                    ),
                    text=(
                        str(item["text"]) if item.get("text") is not None else None
                    ),
                    tag=str(item["tag"]) if item.get("tag") is not None else None,
                    backend_node_id=_snapshot_item_backend_node_id(item),
                    bbox=_snapshot_item_bbox(item),
                    evidence=_snapshot_item_evidence(item),
                    confidence=_snapshot_item_confidence(item),
                )
            )

        refs_tuple = tuple(resolved_items)
        self.ref_store.save_tab_refs(
            profile_name=plan.profile.name,
            target_id=tab.target_id,
            refs=refs_tuple,
        )
        grouped_frames: dict[tuple[int, ...], list[BrowserStoredRef]] = {}
        for item in refs_tuple:
            grouped_frames.setdefault(item.frame_path, []).append(item)
        frames = [
            {
                "frame_path": list(frame_path),
                "snapshot": self._interactive_frame_snapshot(
                    refs=tuple(items),
                    root_selector=root_selector,
                ),
                "refs": self._interactive_refs_payload(
                    refs=tuple(items),
                    snapshot_format=snapshot_format,
                ),
                "ref_count": len(items),
            }
            for frame_path, items in grouped_frames.items()
        ]
        combined_snapshot = _combine_frame_snapshots(frames)
        return {
            "snapshot": combined_snapshot,
            "frames": frames,
            "refs": self._interactive_refs_payload(
                refs=refs_tuple,
                snapshot_format=snapshot_format,
            ),
            "stats": _role_snapshot_stats(snapshot=combined_snapshot, refs=refs_tuple),
        }, len(refs_tuple), len(grouped_frames), generation
