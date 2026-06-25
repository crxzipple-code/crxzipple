from __future__ import annotations

from collections.abc import Callable, Iterable

from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCatalogRecord,
    ToolFunctionStatus,
    ToolSourceCatalogKind,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryRunRecord,
    ToolSourceStatus as CatalogToolSourceStatus,
)
from crxzipple.modules.tool.application.source_commands import (
    ToolSourceCommandService,
)
from crxzipple.modules.tool.application.source_command_models import (
    ToolSourceCatalogSyncResult,
    ToolSourceCommandResult,
    ToolSourceSyncResult,
)
from crxzipple.modules.tool.application.source_runtime_bundles import (
    ToolRuntimeRequestBundle,
    ToolRuntimeRequestBundleGroup,
    build_runtime_request_bundle,
)
from crxzipple.modules.tool.application.source_record_mapping import (
    domain_source_kind as _domain_source_kind,
    domain_source_status as _domain_source_status,
    function_entity_to_record as _function_entity_to_record,
    source_entity_to_record as _source_entity_to_record,
)
from crxzipple.modules.tool.domain.entities import ToolProviderBackend
from crxzipple.modules.tool.domain.value_objects import (
    ToolProviderBackendStatus,
    ToolProviderCapability,
)
from crxzipple.modules.tool.application.source_unit_of_work import (
    ToolSourceUnitOfWork,
)


class ToolSourceQueryService:
    def __init__(self, uow_factory: Callable[[], ToolSourceUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def list_sources(
        self,
        *,
        kind: ToolSourceCatalogKind | str | None = None,
        status: CatalogToolSourceStatus | str | None = None,
    ) -> tuple[ToolSourceCatalogRecord, ...]:
        with self._uow_factory() as uow:
            sources = uow.tool_sources.list(
                kind=_domain_source_kind(kind) if kind is not None else None,
                status=_domain_source_status(status) if status is not None else None,
            )
            return tuple(_source_entity_to_record(source) for source in sources)

    def get_source(self, source_id: str) -> ToolSourceCatalogRecord | None:
        with self._uow_factory() as uow:
            source = uow.tool_sources.get(source_id)
            if source is None:
                return None
            return _source_entity_to_record(source)

    def list_discovery_runs(
        self,
        source_id: str,
        *,
        limit: int = 20,
    ) -> tuple[ToolSourceDiscoveryRunRecord, ...]:
        with self._uow_factory() as uow:
            return uow.tool_source_discovery_runs.list_by_source(
                source_id,
                limit=limit,
            )

    def list_functions(
        self,
        *,
        source_id: str | None = None,
        status: ToolFunctionStatus | str | None = None,
    ) -> tuple[ToolFunctionCatalogRecord, ...]:
        with self._uow_factory() as uow:
            functions = uow.tool_functions.list(
                source_id=source_id,
                status=status,
            )
            return tuple(_function_entity_to_record(function) for function in functions)

    def get_function(self, function_id: str) -> ToolFunctionCatalogRecord | None:
        with self._uow_factory() as uow:
            function = uow.tool_functions.get(function_id)
            if function is None:
                return None
            return _function_entity_to_record(function)

    def list_runtime_request_bundles(
        self,
        function_ids: Iterable[str],
    ) -> tuple[ToolRuntimeRequestBundle, ...]:
        requested_ids = tuple(
            dict.fromkeys(
                str(function_id).strip()
                for function_id in function_ids
                if str(function_id).strip()
            ),
        )
        if not requested_ids:
            return ()

        with self._uow_factory() as uow:
            functions_by_id = uow.tool_functions.list_by_ids(requested_ids)
            function_records = []
            source_ids = []
            for function_id in requested_ids:
                function = functions_by_id.get(function_id)
                if function is None:
                    continue
                function_record = _function_entity_to_record(function)
                if (
                    function_record.status is not ToolFunctionStatus.ACTIVE
                    or not function_record.enabled
                ):
                    continue
                function_records.append(function_record)
                if function_record.source_id not in source_ids:
                    source_ids.append(function_record.source_id)

            sources_by_id = uow.tool_sources.list_by_ids(tuple(source_ids))

        source_records: dict[str, ToolSourceCatalogRecord] = {}
        function_records_by_source: dict[str, list[ToolFunctionCatalogRecord]] = {}
        ordered_source_ids: list[str] = []
        for function_record in function_records:
            source_record = source_records.get(function_record.source_id)
            if source_record is None:
                source = sources_by_id.get(function_record.source_id)
                if source is None:
                    continue
                source_record = _source_entity_to_record(source)
                if source_record.status is not CatalogToolSourceStatus.ACTIVE:
                    continue
                source_records[source_record.source_id] = source_record
                ordered_source_ids.append(source_record.source_id)
            function_records_by_source.setdefault(
                function_record.source_id,
                [],
            ).append(function_record)

        return tuple(
            build_runtime_request_bundle(
                source_records[source_id],
                tuple(function_records_by_source.get(source_id, ())),
            )
            for source_id in ordered_source_ids
            if function_records_by_source.get(source_id)
        )

    def list_provider_backends(
        self,
        *,
        source_id: str | None = None,
        capability: ToolProviderCapability | str | None = None,
        status: ToolProviderBackendStatus | str | None = None,
    ) -> tuple[ToolProviderBackend, ...]:
        with self._uow_factory() as uow:
            return tuple(
                uow.tool_provider_backends.list(
                    source_id=source_id,
                    capability=capability,
                    status=status,
                ),
            )

    def get_provider_backend(self, backend_id: str) -> ToolProviderBackend | None:
        with self._uow_factory() as uow:
            return uow.tool_provider_backends.get(backend_id)


__all__ = [
    "ToolSourceCatalogSyncResult",
    "ToolSourceCommandResult",
    "ToolSourceCommandService",
    "ToolSourceQueryService",
    "ToolSourceSyncResult",
    "ToolSourceUnitOfWork",
]
