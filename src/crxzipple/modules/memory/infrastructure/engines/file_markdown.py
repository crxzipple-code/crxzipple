from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from crxzipple.modules.memory.application.runtime import (
    MemoryEngineCapabilities,
    MemoryRecallRequest,
    MemoryRecallResult,
    MemoryRememberRequest,
    MemoryRememberResult,
    MemoryResolvedLayer,
    recall_item_from_excerpt,
    recall_items_from_hits,
    parse_memory_citation,
)
from crxzipple.modules.memory.application.services import FileBackedMemoryService


@dataclass(frozen=True, slots=True)
class FileMarkdownMemoryEngine:
    service: FileBackedMemoryService

    @property
    def engine_id(self) -> str:
        return "file_markdown"

    def capabilities(self) -> MemoryEngineCapabilities:
        return MemoryEngineCapabilities(
            supports_vector_search=self.service.index_manager.embedding_provider is not None,
            requires_credentials=False,
        )

    def recall(
        self,
        *,
        layers: Sequence[MemoryResolvedLayer],
        request: MemoryRecallRequest,
    ) -> MemoryRecallResult:
        primary_layer = layers[0] if layers else None
        if primary_layer is None:
            raise ValueError("Memory recall requires at least one resolved layer.")
        if request.citation:
            path, start_line, end_line = parse_memory_citation(request.citation)
            target_scope_ref = _optional_metadata_text(
                request.metadata,
                "source_scope_ref",
            )
            citation_layers = (
                tuple(layer for layer in layers if layer.scope_ref == target_scope_ref)
                if target_scope_ref is not None
                else tuple(layers)
            )
            items = []
            for layer in citation_layers:
                excerpt = self.service.get(
                    context=layer.context,
                    path=path,
                    start_line=start_line,
                    line_count=end_line - start_line + 1,
                )
                if excerpt is None:
                    continue
                items.append(recall_item_from_excerpt(excerpt, layer=layer))
                break
            return MemoryRecallResult(
                scope=primary_layer.as_scope(),
                items=tuple(items),
                citation=request.citation,
                searched_layers=tuple(citation_layers),
            )
        query = request.query or ""
        items = []
        seen: set[tuple[str, str, int, int]] = set()
        for layer in layers:
            hits = self.service.search(
                context=layer.context,
                query=query,
                limit=request.max_items,
            )
            for item in recall_items_from_hits(hits, layer=layer):
                key = (
                    item.source_scope_ref or layer.scope_ref,
                    item.path,
                    item.start_line,
                    item.end_line,
                )
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)
        items = sorted(
            items,
            key=lambda item: item.score if item.score is not None else 0.0,
            reverse=True,
        )[: request.max_items]
        return MemoryRecallResult(
            scope=primary_layer.as_scope(),
            items=tuple(items),
            query=query,
            searched_layers=tuple(layers),
        )

    def remember(
        self,
        *,
        layer: MemoryResolvedLayer,
        request: MemoryRememberRequest,
    ) -> MemoryRememberResult:
        result = self.service.append_daily(
            context=layer.context,
            content=request.content,
            title=request.title,
        )
        return MemoryRememberResult(
            scope=layer.as_scope(),
            status="written",
            write_result=result,
            target_layer=layer,
            metadata={
                "engine_id": self.engine_id,
                "intent": request.intent,
                "retention": request.retention,
                "target_scope_ref": layer.scope_ref,
                "target_layer_kind": layer.layer.layer_kind,
            },
        )


def _optional_metadata_text(metadata: object, key: str) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
