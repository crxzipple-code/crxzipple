from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    RecordRequestRenderSnapshotInput,
    RequestRenderSnapshotService,
)
from crxzipple.modules.context_workspace.domain import (
    ContextSnapshot,
    ContextSnapshotNotFoundError,
)
from crxzipple.modules.llm.domain import ToolSchema


class RequestRenderSnapshotRecorder:
    def __init__(
        self,
        service: RequestRenderSnapshotService | None = None,
    ) -> None:
        self._service = service

    @property
    def available(self) -> bool:
        return self._service is not None

    def has_snapshot(self, snapshot_id: str) -> bool:
        if self._service is None:
            return False
        try:
            self._service.get_snapshot(snapshot_id)
        except ContextSnapshotNotFoundError:
            return False
        return True

    def record(
        self,
        *,
        snapshot_id: str,
        workspace_id: str,
        session_key: str,
        run_id: str,
        tree_revision: int,
        model: str,
        input_item_refs: tuple[dict[str, object], ...],
        projected_input_items: tuple[dict[str, object], ...],
        tool_schema_refs: tuple[dict[str, object], ...],
        resource_refs: tuple[dict[str, object], ...],
        estimated_tokens: int,
        render_report: dict[str, object],
        timings: dict[str, float],
        metadata: dict[str, object],
    ) -> str:
        if self._service is None:
            return snapshot_id
        snapshot = self._service.record_snapshot(
            RecordRequestRenderSnapshotInput(
                snapshot_id=snapshot_id,
                workspace_id=workspace_id,
                session_key=session_key,
                run_id=run_id,
                tree_revision=tree_revision,
                turn_id=run_id,
                model=model,
                renderer_id="context_workspace.request_render_snapshot",
                renderer_version="2026-06-18",
                input_item_refs=input_item_refs,
                projected_input_items=projected_input_items,
                tool_schema_refs=tool_schema_refs,
                resource_refs=resource_refs,
                estimated_tokens=estimated_tokens,
                render_report=render_report,
                timings=timings,
                metadata=metadata,
            ),
        )
        return snapshot.id

    def input_item_refs(
        self,
        snapshot: ContextSnapshot,
    ) -> tuple[dict[str, object], ...]:
        request_render_snapshot = self._get_request_render_snapshot(snapshot)
        if request_render_snapshot is None:
            return ()
        return tuple(dict(item) for item in request_render_snapshot.input_item_refs)

    def projected_input_items(
        self,
        snapshot: ContextSnapshot,
    ) -> tuple[dict[str, object], ...]:
        request_render_snapshot = self._get_request_render_snapshot(snapshot)
        if request_render_snapshot is None:
            return ()
        return tuple(dict(item) for item in request_render_snapshot.projected_input_items)

    def tool_schemas(
        self,
        snapshot: ContextSnapshot,
    ) -> tuple[ToolSchema, ...]:
        request_render_snapshot = self._get_request_render_snapshot(snapshot)
        if request_render_snapshot is None:
            return ()
        schemas: list[ToolSchema] = []
        seen: set[str] = set()
        for ref in request_render_snapshot.tool_schema_refs:
            raw_schema = ref.get("schema")
            schema = (
                ToolSchema.from_payload(dict(raw_schema))
                if isinstance(raw_schema, dict)
                else None
            )
            if schema is None:
                raw_name = ref.get("name")
                if not isinstance(raw_name, str) or not raw_name.strip():
                    continue
                schema = ToolSchema(name=raw_name.strip())
            if schema.name in seen:
                continue
            schemas.append(schema)
            seen.add(schema.name)
        return tuple(schemas)

    def tool_schema_refs(
        self,
        snapshot: ContextSnapshot,
    ) -> tuple[dict[str, object], ...]:
        request_render_snapshot = self._get_request_render_snapshot(snapshot)
        if request_render_snapshot is None:
            return ()
        return tuple(dict(ref) for ref in request_render_snapshot.tool_schema_refs)

    def _get_request_render_snapshot(self, snapshot: ContextSnapshot) -> object | None:
        if snapshot.metadata.get("snapshot_kind") != "request_render":
            return None
        if self._service is None:
            return None
        try:
            return self._service.get_snapshot(snapshot.id)
        except ContextSnapshotNotFoundError:
            return None
