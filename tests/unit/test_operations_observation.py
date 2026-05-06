from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from crxzipple.core.db import Base, import_models
from crxzipple.modules.events import EventsApplicationService, InMemoryEventsBackend
from crxzipple.modules.events.domain import EventTopicRecord
from crxzipple.modules.operations.application.observation import (
    OperationsModuleObservation,
    OperationsProjection,
    observed_event_from_record,
)
from crxzipple.modules.operations.application.projections import (
    OPERATIONS_PROJECTION_INVALIDATED_EVENT,
    OperationsProjectionMaterializer,
)
from crxzipple.modules.operations.application.read_models.orchestration import (
    OrchestrationOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.runtime import (
    operations_observer_event_names,
)
from crxzipple.modules.operations.infrastructure import (
    FileBackedOperationsObservationStore,
)
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationExecutorLease,
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.operations.infrastructure.persistence import (
    SqlAlchemyOperationsActionAuditStore,
    SqlAlchemyOperationsProjectionStore,
)
from crxzipple.modules.operations.interfaces.http import (
    _operations_action_audit_payload,
    _validated_operations_action,
)
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsActionReasonRequest,
    OperationsChannelRuntimePruneRequest,
)
from crxzipple.shared.domain.events import Event, named_event_topic


class OperationsObservationTestCase(unittest.TestCase):
    def test_file_backed_store_records_orchestration_module_observation(self) -> None:
        timestamp = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tempdir:
            store = FileBackedOperationsObservationStore(tempdir)

            self._record(
                store,
                cursor="1",
                name="orchestration.run.accepted",
                payload={
                    "run_id": "run-ops-1",
                    "source": "http",
                    "status": "accepted",
                    "stage": "accepted",
                    "priority": 7,
                },
                occurred_at=timestamp,
            )
            self._record(
                store,
                cursor="2",
                name="orchestration.run.queued",
                payload={
                    "run_id": "run-ops-1",
                    "status": "queued",
                    "stage": "queued",
                    "lane_key": "session:assistant:main",
                    "priority": 7,
                },
                occurred_at=timestamp + timedelta(seconds=1),
            )
            self._record(
                store,
                cursor="3",
                name="orchestration.run.claimed",
                payload={
                    "run_id": "run-ops-1",
                    "status": "running",
                    "stage": "running",
                    "worker_id": "executor-1",
                    "lane_lock_key": "session:assistant:main",
                },
                occurred_at=timestamp + timedelta(seconds=2),
            )
            self._record(
                store,
                cursor="4",
                name="orchestration.run.completed",
                payload={
                    "run_id": "run-ops-1",
                    "status": "completed",
                    "stage": "completed",
                    "worker_id": "executor-1",
                },
                occurred_at=timestamp + timedelta(seconds=3),
            )
            self._record(
                store,
                cursor="5",
                name="orchestration.ingress.requested",
                payload={
                    "request_id": "ingress-1",
                    "run_id": "run-ops-1",
                    "kind": "routed_turn",
                    "status": "queued",
                    "source": "web",
                    "target_lane": "session:assistant:main",
                    "priority": 7,
                },
                occurred_at=timestamp + timedelta(seconds=4),
            )
            self._record(
                store,
                cursor="6",
                name="orchestration.ingress.completed",
                payload={
                    "request_id": "ingress-1",
                    "run_id": "run-ops-1",
                    "kind": "routed_turn",
                    "status": "completed",
                },
                occurred_at=timestamp + timedelta(seconds=5),
            )
            self._record(
                store,
                cursor="7",
                name="orchestration.scheduler.signal.requested",
                payload={
                    "signal_id": "tool-terminal:tool-1",
                    "signal_kind": "tool_terminal",
                    "status": "queued",
                },
                occurred_at=timestamp + timedelta(seconds=6),
            )
            self._record(
                store,
                cursor="8",
                name="orchestration.scheduler.signal.claimed",
                payload={
                    "signal_id": "tool-terminal:tool-1",
                    "signal_kind": "tool_terminal",
                    "status": "processing",
                    "worker_id": "scheduler-1",
                },
                occurred_at=timestamp + timedelta(seconds=7),
            )
            self._record(
                store,
                cursor="9",
                name="orchestration.executor.lease.heartbeated",
                payload={
                    "worker_id": "executor-1",
                    "status": "online",
                    "max_inflight_assignments": 3,
                    "inflight_assignment_count": 1,
                    "available_assignment_slots": 2,
                    "active_run_ids": ["run-ops-1"],
                    "lease_expires_at": "2026-05-01T10:00:39+00:00",
                },
                occurred_at=timestamp + timedelta(seconds=8),
            )

            observation = store.get_module_observation("orchestration")
            self.assertIsNotNone(observation)
            assert observation is not None
            self.assertFalse(hasattr(store.snapshot(), "orchestration"))
            self.assertEqual(observation.last_cursor, "9")
            self.assertEqual(observation.event_count, 9)
            self.assertEqual(
                observation.last_event_name,
                "orchestration.executor.lease.heartbeated",
            )
            self.assertEqual(observation.recent_events[0].run_id, None)
            self.assertEqual(
                observation.recent_events[-1].event_name,
                "orchestration.run.accepted",
            )
            persisted_payload = json.loads(
                (Path(tempdir) / "observer_observation.json").read_text(
                    encoding="utf-8",
                ),
            )
            self.assertNotIn("orchestration", persisted_payload)

            restored = FileBackedOperationsObservationStore(tempdir)
            restored_observation = restored.get_module_observation("orchestration")
            self.assertIsNotNone(restored_observation)
            assert restored_observation is not None
            self.assertEqual(restored_observation.event_count, 9)
            self.assertEqual(restored_observation.last_cursor, "9")

    def test_operations_observer_subscribes_raw_orchestration_events(self) -> None:
        names = set(operations_observer_event_names())

        self.assertIn("orchestration.run.accepted", names)
        self.assertIn("orchestration.ingress.claimed", names)
        self.assertIn("orchestration.scheduler.signal.completed", names)
        self.assertIn("orchestration.executor.assignment.requested", names)
        self.assertIn("tool.run.created", names)
        self.assertIn("tool.assignment.created", names)

    def test_sqlalchemy_store_records_operations_projection(self) -> None:
        timestamp = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
        engine = create_engine("sqlite:///:memory:")
        import_models()
        Base.metadata.create_all(engine)
        store = SqlAlchemyOperationsProjectionStore(
            sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
        )

        store.record_projection(
            module="tool",
            kind="page",
            payload={
                "module": "tool",
                "title": "Tool Runtime",
                "rows": [{"id": "tool_run_1"}],
            },
            updated_at=timestamp,
        )

        projection = store.get_projection(module="tool", kind="page")
        self.assertIsNotNone(projection)
        assert projection is not None
        self.assertEqual(projection.module, "tool")
        self.assertEqual(projection.kind, "page")
        self.assertEqual(projection.payload["title"], "Tool Runtime")
        self.assertEqual(projection.payload["rows"][0]["id"], "tool_run_1")

        store.record_projection(
            module="tool",
            kind="page",
            payload={"module": "tool", "title": "Tool Runtime Updated"},
            updated_at=timestamp + timedelta(seconds=1),
        )
        updated = store.get_projection(module="tool", kind="page")
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.payload["title"], "Tool Runtime Updated")

    def test_sqlalchemy_store_records_operations_action_audit_lifecycle(self) -> None:
        timestamp = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
        engine = create_engine("sqlite:///:memory:")
        import_models()
        Base.metadata.create_all(engine)
        store = SqlAlchemyOperationsActionAuditStore(
            sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
        )

        audit = store.record_attempt(
            action_type="events.subscriptions.advance_to_head",
            target_type="event_subscription",
            target_id="sub-1",
            target={"subscription_id": "sub-1"},
            reason="repair stuck cursor",
            dangerous=True,
            risk="dangerous",
            confirmation=True,
            risk_acknowledged=True,
            operator="ops-user",
            source="operations-ui",
            metadata={"ticket": "OPS-1"},
            created_at=timestamp,
        )

        self.assertEqual(audit.status, "attempted")
        self.assertTrue(audit.dangerous)
        self.assertEqual(audit.reason, "repair stuck cursor")
        self.assertEqual(audit.metadata["ticket"], "OPS-1")

        succeeded = store.mark_succeeded(
            audit.audit_id,
            result={"advanced_count": 1},
            updated_at=timestamp + timedelta(seconds=1),
        )

        self.assertEqual(succeeded.status, "succeeded")
        self.assertEqual(succeeded.result, {"advanced_count": 1})
        recent = store.list_recent(limit=10)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].audit_id, audit.audit_id)

        failed = store.record_attempt(
            action_type="channels.runtimes.prune_stale",
            target_type="channel_runtime",
            target_id="runtime-1",
            target={"runtime_id": "runtime-1"},
            reason="cleanup stale runtime",
            dangerous=True,
            risk="dangerous",
            confirmation=True,
            risk_acknowledged=True,
            operator=None,
            source="operations",
            metadata={},
            created_at=timestamp + timedelta(seconds=2),
        )
        failed = store.mark_failed(
            failed.audit_id,
            error={"type": "HTTPException", "status_code": 400},
        )

        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error["status_code"], 400)

    def test_tool_materializer_stores_run_details_outside_page_projection(self) -> None:
        store = self._projection_store()
        store.record_projection(
            module="tool",
            kind="tool_run_detail",
            query_key="stale-tool-run",
            payload={"run_id": "stale-tool-run", "input_payload": {"old": True}},
        )
        materializer = OperationsProjectionMaterializer(
            source_provider=_FakeOperationsSourceProvider(),
            projection_store=store,
        )

        materialized = materializer.materialize_modules(("tool",))

        self.assertEqual(materialized, 1)
        page_projection = store.get_projection(module="tool", kind="page")
        self.assertIsNotNone(page_projection)
        assert page_projection is not None
        self.assertEqual(page_projection.payload["tool_run_details"], [])
        detail = store.get_projection(
            module="tool",
            kind="tool_run_detail",
            query_key="tool-run-2",
        )
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail.payload["input_payload"], {"large": "two"})
        self.assertIsNone(
            store.get_projection(
                module="tool",
                kind="tool_run_detail",
                query_key="stale-tool-run",
            ),
        )

    def test_llm_materializer_stores_invocation_details_outside_page_projection(
        self,
    ) -> None:
        store = self._projection_store()
        store.record_projection(
            module="llm",
            kind="llm_invocation_detail",
            query_key="stale-llm-invocation",
            payload={
                "invocation_id": "stale-llm-invocation",
                "request_payload": {"old": True},
            },
        )
        materializer = OperationsProjectionMaterializer(
            source_provider=_FakeOperationsSourceProvider(),
            projection_store=store,
        )

        materialized = materializer.materialize_modules(("llm",))

        self.assertEqual(materialized, 1)
        page_projection = store.get_projection(module="llm", kind="page")
        self.assertIsNotNone(page_projection)
        assert page_projection is not None
        self.assertEqual(page_projection.payload["invocation_details"], [])
        detail = store.get_projection(
            module="llm",
            kind="llm_invocation_detail",
            query_key="llm-invocation-2",
        )
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail.payload["request_payload"], {"large": "two"})
        self.assertIsNone(
            store.get_projection(
                module="llm",
                kind="llm_invocation_detail",
                query_key="stale-llm-invocation",
            ),
        )

    def test_orchestration_page_uses_module_observation_without_rich_snapshot(self) -> None:
        timestamp = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        observed_event = observed_event_from_record(
            EventTopicRecord(
                cursor="cursor-owner",
                envelope=Event(
                    name="orchestration.run.queued",
                    payload={
                        "run_id": "run-owner-query",
                        "status": "queued",
                        "stage": "queued",
                    },
                    occurred_at=timestamp,
                ),
            ),
        )
        provider = OrchestrationOperationsReadModelProvider(
            run_query=_FakeOrchestrationRunQuery(
                runs=[
                    OrchestrationRun(
                        id="run-owner-query",
                        inbound_instruction=InboundInstruction(
                            source="http",
                            content="owner truth",
                        ),
                        status=OrchestrationRunStatus.QUEUED,
                        stage=OrchestrationRunStage.QUEUED,
                        lane_key="session:agent:assistant:main",
                        priority=4,
                        metadata={"trace_id": "trace-owner-query"},
                        created_at=timestamp,
                        updated_at=timestamp,
                        queued_at=timestamp,
                    ),
                ],
            ),
            executor_control=_FakeOrchestrationExecutorControl(
                leases=[
                    OrchestrationExecutorLease(
                        id="worker-owner-query",
                        max_inflight_assignments=3,
                        inflight_assignment_count=1,
                        created_at=timestamp,
                        updated_at=timestamp,
                        last_heartbeat_at=timestamp,
                        lease_expires_at=timestamp + timedelta(seconds=30),
                    ),
                ],
            ),
            operations_observation=_ModuleOnlyOperationsObservation(
                OperationsModuleObservation(
                    module="orchestration",
                    owner="orchestration",
                    updated_at=timestamp,
                    event_count=1,
                    last_event_name="orchestration.run.queued",
                    last_cursor="cursor-owner",
                    last_event_at=timestamp,
                    recent_events=(observed_event,),
                ),
            ),
        )

        page = provider.page()

        run_ids = {row.cells["run_id"] for row in page.run_queue.rows}
        executor_ids = {row.cells["worker_id"] for row in page.executor_overview.rows}
        metrics = {metric.id: metric for metric in page.metrics}
        scheduler_items = {
            item.label: item.value for item in page.scheduler_status.items
        }
        self.assertEqual(run_ids, {"run-owner-query"})
        self.assertNotIn("run-poisoned-file-observation", run_ids)
        self.assertEqual(executor_ids, {"worker-owner-query"})
        self.assertEqual(metrics["observed_facts"].value, "1")
        self.assertIn("last orchestration.run.queued", metrics["observed_facts"].delta)
        self.assertEqual(scheduler_items["Observed Cursor"], "cursor-owner")
        self.assertEqual(
            scheduler_items["Observed Entities"],
            "1 total / 1 recent / last orchestration.run.queued",
        )

    def test_materializer_stores_paginated_tables_outside_page_projection(
        self,
    ) -> None:
        store = self._projection_store()
        materializer = OperationsProjectionMaterializer(
            source_provider=_PaginatedOperationsSourceProvider(total=75),
            projection_store=store,
        )

        materialized = materializer.materialize_modules(("tool", "llm"))

        self.assertEqual(materialized, 2)
        tool_page = store.get_projection(module="tool", kind="page")
        tool_table = store.get_projection(
            module="tool",
            kind="table",
            query_key="tool_runs",
        )
        tool_detail = store.get_projection(
            module="tool",
            kind="tool_run_detail",
            query_key="tool-run-74",
        )
        self.assertIsNotNone(tool_page)
        self.assertIsNotNone(tool_table)
        self.assertIsNotNone(tool_detail)
        assert tool_page is not None
        assert tool_table is not None
        assert tool_detail is not None
        self.assertEqual(len(tool_page.payload["tool_runs"]["rows"]), 50)
        self.assertEqual(len(tool_table.payload["rows"]), 75)
        self.assertEqual(tool_table.payload["total"], 75)
        self.assertEqual(tool_detail.payload["input_payload"], {"index": 74})

        llm_page = store.get_projection(module="llm", kind="page")
        llm_table = store.get_projection(
            module="llm",
            kind="table",
            query_key="recent_invocations",
        )
        llm_detail = store.get_projection(
            module="llm",
            kind="llm_invocation_detail",
            query_key="llm-invocation-74",
        )
        self.assertIsNotNone(llm_page)
        self.assertIsNotNone(llm_table)
        self.assertIsNotNone(llm_detail)
        assert llm_page is not None
        assert llm_table is not None
        assert llm_detail is not None
        self.assertEqual(len(llm_page.payload["recent_invocations"]["rows"]), 50)
        self.assertEqual(len(llm_table.payload["rows"]), 75)
        self.assertEqual(llm_table.payload["total"], 75)
        self.assertEqual(llm_detail.payload["request_payload"], {"index": 74})

    def test_materializer_clears_stale_details_when_current_page_has_none(self) -> None:
        store = self._projection_store()
        store.record_projection(
            module="tool",
            kind="tool_run_detail",
            query_key="stale-tool-run",
            payload={"run_id": "stale-tool-run"},
        )
        store.record_projection(
            module="llm",
            kind="llm_invocation_detail",
            query_key="stale-llm-invocation",
            payload={"invocation_id": "stale-llm-invocation"},
        )
        materializer = OperationsProjectionMaterializer(
            source_provider=_EmptyDetailOperationsSourceProvider(),
            projection_store=store,
        )

        materializer.materialize_modules(("tool", "llm"))

        self.assertIsNone(
            store.get_projection(
                module="tool",
                kind="tool_run_detail",
                query_key="stale-tool-run",
            ),
        )
        self.assertIsNone(
            store.get_projection(
                module="llm",
                kind="llm_invocation_detail",
                query_key="stale-llm-invocation",
            ),
        )

    def test_operations_projection_round_trips_payload(self) -> None:
        timestamp = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
        projection = OperationsProjection(
            module="tool",
            kind="page",
            query_key="default",
            updated_at=timestamp,
            payload={"title": "Tool Runtime"},
        )

        restored = OperationsProjection.from_payload(projection.to_payload())

        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.module, "tool")
        self.assertEqual(restored.kind, "page")
        self.assertEqual(restored.query_key, "default")
        self.assertEqual(restored.updated_at, timestamp)
        self.assertEqual(restored.payload["title"], "Tool Runtime")

    def test_projection_materializer_publishes_operations_invalidation(self) -> None:
        backend = InMemoryEventsBackend()
        events_service = EventsApplicationService(backend)
        projection_store = _FakeProjectionStore()
        materializer = OperationsProjectionMaterializer(
            source_provider=_FakeOperationsSourceProvider(),
            projection_store=projection_store,
            events_service=events_service,
        )

        materialized = materializer.materialize_modules(("orchestration",))

        self.assertEqual(materialized, 1)
        self.assertIn(("orchestration", "page"), projection_store.records)
        records = events_service.read_recent_event_topic(
            named_event_topic(OPERATIONS_PROJECTION_INVALIDATED_EVENT),
            limit=10,
        )
        self.assertEqual(len(records), 1)
        payload = records[0].envelope.payload
        self.assertEqual(payload["module"], "orchestration")
        self.assertEqual(payload["kinds"], ["page", "overview"])
        self.assertEqual(payload["source"], "operations-observer")

    def test_operations_action_request_accepts_audit_payload(self) -> None:
        request = OperationsActionReasonRequest(
            reason=" operator requested restart ",
            confirmation=True,
            risk_acknowledged=True,
            operator="ops-user",
            source="operations-ui",
            metadata={"ticket": "OPS-1"},
        )

        reason = _validated_operations_action(
            request,
            default_reason="Operations default action reason",
            risk="dangerous",
        )

        self.assertEqual(reason, "operator requested restart")

    def test_operations_dangerous_action_requires_reason_confirmation_and_risk_ack(
        self,
    ) -> None:
        with self.assertRaises(Exception) as reason_error:
            _validated_operations_action(
                OperationsChannelRuntimePruneRequest(
                    reason="",
                    confirmation=True,
                    risk_acknowledged=True,
                ),
                default_reason="Operations stale channel runtime prune",
                risk="dangerous",
            )
        self.assertIn(
            "reason is required for this operations action",
            str(getattr(reason_error.exception, "detail", reason_error.exception)),
        )

        with self.assertRaises(Exception) as confirmation_error:
            _validated_operations_action(
                OperationsChannelRuntimePruneRequest(
                    reason="clear stale channel runtime",
                    risk_acknowledged=True,
                ),
                default_reason="Operations stale channel runtime prune",
                risk="dangerous",
            )
        self.assertIn(
            "confirmation is required for this operations action",
            str(getattr(confirmation_error.exception, "detail", confirmation_error.exception)),
        )

        with self.assertRaises(Exception) as risk_error:
            _validated_operations_action(
                OperationsChannelRuntimePruneRequest(
                    reason="clear stale channel runtime",
                    confirmation=True,
                ),
                default_reason="Operations stale channel runtime prune",
                risk="dangerous",
            )
        self.assertIn(
            "risk acknowledgement is required for this operations action",
            str(getattr(risk_error.exception, "detail", risk_error.exception)),
        )

    def test_operations_normal_action_uses_default_reason(self) -> None:
        reason = _validated_operations_action(
            OperationsActionReasonRequest(),
            default_reason="Operations tool run retry",
        )

        self.assertEqual(reason, "Operations tool run retry")

    def test_operations_action_audit_payload_preserves_controlled_risk(self) -> None:
        payload = _operations_action_audit_payload(
            OperationsActionReasonRequest(
                reason="retry tool run",
                confirmation=True,
                metadata={"ticket": "OPS-2"},
            ),
            reason="retry tool run",
            risk="controlled",
        )

        self.assertEqual(payload["risk"], "controlled")
        self.assertFalse(payload["dangerous"])
        self.assertTrue(payload["confirmation"])
        self.assertEqual(payload["metadata"], {"ticket": "OPS-2"})

    def test_file_backed_store_observes_tool_module_events(self) -> None:
        timestamp = datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tempdir:
            store = FileBackedOperationsObservationStore(tempdir)

            self._record(
                store,
                cursor="tool-1",
                name="tool.run.succeeded",
                payload={
                    "run_id": "tool-run-1",
                    "tool_id": "echo",
                    "status": "succeeded",
                },
                occurred_at=timestamp,
            )

            observation = store.get_module_observation("tool")

            self.assertIsNotNone(observation)
            assert observation is not None
            self.assertEqual(observation.event_count, 1)
            self.assertEqual(observation.last_event_name, "tool.run.succeeded")
            self.assertEqual(observation.recent_events[0].run_id, "tool-run-1")
            self.assertEqual(observation.recent_events[0].trace_id, None)

    @staticmethod
    def _projection_store() -> SqlAlchemyOperationsProjectionStore:
        engine = create_engine("sqlite:///:memory:")
        import_models()
        Base.metadata.create_all(engine)
        return SqlAlchemyOperationsProjectionStore(
            sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
        )

    @staticmethod
    def _record(
        store: FileBackedOperationsObservationStore,
        *,
        cursor: str,
        name: str,
        payload: dict[str, object],
        occurred_at: datetime,
    ) -> None:
        event = Event(name=name, payload=payload, occurred_at=occurred_at)
        store.record_observed_event(
            observed_event_from_record(
                EventTopicRecord(cursor=cursor, envelope=event),
            ),
        )


class _FakeProjectionStore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict[str, object]] = {}

    def record_projection(
        self,
        *,
        module: str,
        kind: str,
        payload: dict[str, object],
        query_key: str = "default",
        updated_at: datetime | None = None,
    ) -> None:
        self.records[(module, kind)] = {
            "payload": payload,
            "query_key": query_key,
            "updated_at": updated_at,
        }

    def clear(self, *, module: str | None = None, kind: str | None = None) -> int:
        removed = 0
        for key in tuple(self.records):
            record_module, record_kind = key
            if module is not None and record_module != module:
                continue
            if kind is not None and record_kind != kind:
                continue
            del self.records[key]
            removed += 1
        return removed


class _FakeOrchestrationRunQuery:
    def __init__(self, runs: list[OrchestrationRun]) -> None:
        self._runs = tuple(runs)

    def list_runs(self, *, status: object | None = None) -> list[OrchestrationRun]:
        del status
        return list(self._runs)


class _FakeOrchestrationExecutorControl:
    def __init__(self, leases: list[OrchestrationExecutorLease]) -> None:
        self._leases = tuple(leases)

    def list_executor_leases(
        self,
        *,
        status: object | None = None,
    ) -> list[OrchestrationExecutorLease]:
        del status
        return list(self._leases)


class _ModuleOnlyOperationsObservation:
    def __init__(self, module_observation: OperationsModuleObservation) -> None:
        self._module_observation = module_observation

    def get_module_observation(
        self,
        module: str,
    ) -> OperationsModuleObservation | None:
        return self._module_observation if module == "orchestration" else None


class _FakeOperationsSourceProvider:
    def orchestration_page(self) -> dict[str, object]:
        return {"module": "orchestration", "title": "Orchestration"}

    def tool_page(self, query: object | None = None) -> dict[str, object]:
        del query
        return {
            "module": "tool",
            "title": "Tool Runtime",
            "tool_run_details": [
                {"run_id": "tool-run-1", "input_payload": {"large": "one"}},
                {"run_id": "tool-run-2", "input_payload": {"large": "two"}},
            ],
        }

    def llm_page(self, query: object | None = None) -> dict[str, object]:
        del query
        return {
            "module": "llm",
            "title": "LLM Runtime",
            "invocation_details": [
                {
                    "invocation_id": "llm-invocation-1",
                    "request_payload": {"large": "one"},
                },
                {
                    "invocation_id": "llm-invocation-2",
                    "request_payload": {"large": "two"},
                },
            ],
        }

    def module_overview(self, module: str) -> dict[str, object]:
        return {"module": module, "title": module.title()}


class _EmptyDetailOperationsSourceProvider(_FakeOperationsSourceProvider):
    def tool_page(self, query: object | None = None) -> dict[str, object]:
        del query
        return {
            "module": "tool",
            "title": "Tool Runtime",
            "tool_run_details": [],
        }

    def llm_page(self, query: object | None = None) -> dict[str, object]:
        del query
        return {
            "module": "llm",
            "title": "LLM Runtime",
            "invocation_details": [],
        }


class _PaginatedOperationsSourceProvider(_FakeOperationsSourceProvider):
    def __init__(self, *, total: int) -> None:
        self.total = total

    def tool_page(self, query: object | None = None) -> dict[str, object]:
        offset = _query_int(query, "offset", 0)
        limit = _query_int(query, "limit", 50)
        indexes = range(offset, min(offset + limit, self.total))
        return {
            "module": "tool",
            "title": "Tool Runtime",
            "tool_runs": {
                "id": "tool_runs",
                "title": "Tool Runs",
                "columns": [],
                "rows": [
                    {"id": f"tool-run-{index}", "cells": {"index": str(index)}}
                    for index in indexes
                ],
                "total": self.total,
            },
            "tool_run_details": [
                {
                    "run_id": f"tool-run-{index}",
                    "input_payload": {"index": index},
                }
                for index in indexes
            ],
        }

    def llm_page(self, query: object | None = None) -> dict[str, object]:
        offset = _query_int(query, "offset", 0)
        limit = _query_int(query, "limit", 50)
        indexes = range(offset, min(offset + limit, self.total))
        return {
            "module": "llm",
            "title": "LLM Runtime",
            "recent_invocations": {
                "id": "recent_invocations",
                "title": "Recent Invocations",
                "columns": [],
                "rows": [
                    {
                        "id": f"llm-invocation-{index}",
                        "cells": {"index": str(index)},
                    }
                    for index in indexes
                ],
                "total": self.total,
            },
            "invocation_details": [
                {
                    "invocation_id": f"llm-invocation-{index}",
                    "request_payload": {"index": index},
                }
                for index in indexes
            ],
        }


def _query_int(query: object | None, name: str, default: int) -> int:
    value = getattr(query, name, default)
    return value if isinstance(value, int) else default


if __name__ == "__main__":
    unittest.main()
