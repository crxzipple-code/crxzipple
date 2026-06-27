from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError

from .cdp_sessions import display_safe_cdp_error
from .storage_cdp import page_security_origin, send_cdp_session_command
from .storage_payloads import (
    payload_bool_any,
    payload_limit,
    payload_skip,
    payload_text_any,
    payload_value_any,
)
from .storage_result_projection import BrowserStorageResultProjector


@dataclass(frozen=True, slots=True)
class BrowserIndexedDbStorageInspector:
    projector: BrowserStorageResultProjector = field(
        default_factory=BrowserStorageResultProjector,
    )

    def execute(
        self,
        *,
        page: Any,
        session: Any,
        kind: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        origin = page_security_origin(page, payload)
        if kind == "storage-indexeddb-list":
            return self._list_databases(session=session, payload=payload, origin=origin, kind=kind)
        return self._query_database(
            session=session,
            payload=payload,
            origin=origin,
            kind=kind,
        )

    def _list_databases(
        self,
        *,
        session: Any,
        payload: Mapping[str, Any],
        origin: str,
        kind: str,
    ) -> dict[str, Any]:
        names_payload = send_cdp_session_command(
            session,
            "IndexedDB.requestDatabaseNames",
            {"securityOrigin": origin},
        )
        raw_names = (
            names_payload.get("databaseNames")
            if isinstance(names_payload, Mapping)
            else None
        )
        database_names = (
            [
                str(name)
                for name in raw_names
                if isinstance(name, str) and name.strip()
            ]
            if isinstance(raw_names, list)
            else []
        )
        include_metadata = payload_bool_any(
            payload,
            "include_metadata",
            "includeMetadata",
        )
        if include_metadata is None:
            include_metadata = True
        databases: list[dict[str, Any]] = []
        if include_metadata:
            for database_name in database_names:
                try:
                    raw_database = send_cdp_session_command(
                        session,
                        "IndexedDB.requestDatabase",
                        {
                            "securityOrigin": origin,
                            "databaseName": database_name,
                        },
                    )
                except Exception as exc:  # pragma: no cover - CDP support varies by target
                    databases.append(
                        {
                            "name": database_name,
                            "error": display_safe_cdp_error(
                                exc,
                                operation="IndexedDB.requestDatabase",
                            ),
                        }
                    )
                    continue
                databases.append(self.projector.indexeddb_database(raw_database))
        return {
            "kind": kind,
            "origin": origin,
            "database_names": database_names,
            "databases": databases,
            "count": len(database_names),
        }

    def _query_database(
        self,
        *,
        session: Any,
        payload: Mapping[str, Any],
        origin: str,
        kind: str,
    ) -> dict[str, Any]:
        database_name = payload_text_any(payload, "database_name", "databaseName")
        object_store_name = payload_text_any(
            payload,
            "object_store_name",
            "objectStoreName",
            "store",
        )
        if database_name is None or object_store_name is None:
            raise BrowserValidationError(
                "payload.database_name and payload.object_store_name are required.",
            )
        index_name = payload_text_any(payload, "index_name", "indexName")
        limit = payload_limit(payload, default=50)
        skip = payload_skip(payload)
        raw_data = send_cdp_session_command(
            session,
            "IndexedDB.requestData",
            {
                "securityOrigin": origin,
                "databaseName": database_name,
                "objectStoreName": object_store_name,
                "indexName": index_name or "",
                "skipCount": skip,
                "pageSize": limit,
            },
        )
        raw_entries = (
            raw_data.get("objectStoreDataEntries")
            if isinstance(raw_data, Mapping)
            else None
        )
        entries = (
            [
                self.projector.indexeddb_entry(raw_entry)
                for raw_entry in raw_entries
                if isinstance(raw_entry, Mapping)
            ]
            if isinstance(raw_entries, list)
            else []
        )
        if kind == "storage-indexeddb-get":
            key = payload_value_any(payload, "key", "primary_key", "primaryKey")
            if key is None:
                raise BrowserValidationError("payload.key is required for indexeddb get.")
            key_text = str(key)
            entries = [
                entry
                for entry in entries
                if str(entry.get("key")) == key_text
                or str(entry.get("primary_key")) == key_text
            ][:1]
        return {
            "kind": kind,
            "origin": origin,
            "database_name": database_name,
            "object_store_name": object_store_name,
            "index_name": index_name,
            "skip": skip,
            "limit": limit,
            "entries": entries,
            "count": len(entries),
            "has_more": bool(raw_data.get("hasMore"))
            if isinstance(raw_data, Mapping)
            else False,
        }


__all__ = ["BrowserIndexedDbStorageInspector"]
