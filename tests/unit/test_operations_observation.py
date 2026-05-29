from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from crxzipple.core.db import Base, import_models
from crxzipple.app.assembly.events import build_event_definition_registry
from crxzipple.modules.events import EventsApplicationService, InMemoryEventsBackend
from crxzipple.modules.events.domain import EventTopicRecord
from crxzipple.modules.browser.application.events import BROWSER_OPERATION_EVENT_NAMES
from crxzipple.modules.memory.application.events import MEMORY_OPERATION_EVENT_NAMES
from crxzipple.app.assembly.event_runtime import OPERATIONS_STATE_PROJECTION_MODULES
from crxzipple.modules.operations.application.observation import (
    OperationsModuleObservation,
    OperationsObserverHeartbeat,
    OperationsObservedEvent,
    OperationsObservationSnapshot,
    OperationsProjection,
    observed_event_from_record,
)
from crxzipple.modules.operations.application.projections import (
    OPERATIONS_PROJECTION_MODULES,
    OPERATIONS_PROJECTION_INVALIDATED_EVENT,
    OperationsProjectionMaterializer,
)
from crxzipple.modules.operations.application.read_models.orchestration import (
    OrchestrationOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.access import (
    AccessOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.memory import (
    MemoryOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.skills import (
    SkillsOperationsReadModelProvider,
)
from crxzipple.modules.operations.application.read_models.events import (
    EventsOperationsReadModelProvider,
    _health as events_operations_health,
)
from crxzipple.modules.operations.application.runtime import (
    OperationsObserverRuntimeService,
    operations_observer_event_names,
)
from crxzipple.modules.skills.application.events import (
    SKILL_DRAFT_APPLIED_EVENT,
    SKILL_DRAFT_APPLY_FAILED_EVENT,
    SKILL_DRAFT_CREATED_EVENT,
    SKILL_DRAFT_VALIDATED_EVENT,
    SKILL_OPERATION_EVENT_NAMES,
    SKILL_READ_SUCCEEDED_EVENT,
    SKILL_RESOLUTION_COMPLETED_EVENT,
)
from crxzipple.modules.access.application.events import (
    ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT,
    ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT,
    ACCESS_OPERATION_EVENT_NAMES,
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
from crxzipple.modules.skills.application import SkillPackage
from crxzipple.modules.skills.domain import SkillManifest
from crxzipple.modules.operations.infrastructure.persistence import (
    SqlAlchemyOperationsObservationStore,
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

    def test_sqlalchemy_store_persists_observations_and_time_buckets(self) -> None:
        timestamp = datetime(2026, 5, 23, 10, 15, tzinfo=timezone.utc)
        engine = create_engine("sqlite:///:memory:")
        import_models()
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            expire_on_commit=False,
        )
        store = SqlAlchemyOperationsObservationStore(session_factory)
        succeeded = observed_event_from_record(
            EventTopicRecord(
                cursor="access-1",
                envelope=Event(
                    name=ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT,
                    payload={
                        "target_id": "openai-api-key",
                        "status": "succeeded",
                    },
                    occurred_at=timestamp,
                ),
            ),
        )
        failed = observed_event_from_record(
            EventTopicRecord(
                cursor="access-2",
                envelope=Event(
                    name=ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT,
                    payload={
                        "target_id": "missing-api-key",
                        "status": "failed",
                        "reason": "missing",
                    },
                    occurred_at=timestamp + timedelta(minutes=12),
                ),
            ),
        )

        store.record_observed_events((succeeded, failed))
        store.record_observed_event(succeeded)
        store.record_observer_heartbeat(
            OperationsObserverHeartbeat(
                runtime_name="operations.observer",
                worker_id="observer-1",
                status="running",
                started_at=timestamp,
                last_seen_at=timestamp + timedelta(minutes=13),
                processed_events=2,
                idle_cycles=0,
                subscription_count=12,
                poll_interval_seconds=0.5,
                limit_per_subscription=100,
            ),
        )

        restored = SqlAlchemyOperationsObservationStore(session_factory)
        observation = restored.get_module_observation("access")
        self.assertIsNotNone(observation)
        assert observation is not None
        self.assertEqual(observation.event_count, 2)
        self.assertEqual(observation.status_counts["succeeded"], 1)
        self.assertEqual(observation.status_counts["failed"], 1)
        self.assertEqual(observation.recent_events[0].event_name, ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT)
        self.assertEqual(observation.recent_events[1].event_name, ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT)

        buckets = restored.list_event_buckets(module="access")
        bucket_counts = {
            (bucket["event_name"], bucket["status"]): bucket["count"]
            for bucket in buckets
        }
        self.assertEqual(
            bucket_counts[
                (ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT, "succeeded")
            ],
            1,
        )
        self.assertEqual(
            bucket_counts[(ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT, "failed")],
            1,
        )
        snapshot = restored.snapshot()
        self.assertEqual(len(snapshot.observer_heartbeats), 1)
        self.assertEqual(snapshot.observer_heartbeats[0].worker_id, "observer-1")

    def test_operations_observer_subscribes_raw_orchestration_events(self) -> None:
        names = set(operations_observer_event_names())

        self.assertIn("orchestration.run.accepted", names)
        self.assertIn("orchestration.ingress.claimed", names)
        self.assertIn("orchestration.scheduler.signal.completed", names)
        self.assertIn("orchestration.executor.assignment.requested", names)
        self.assertIn("tool.run.created", names)
        self.assertIn("tool.assignment.created", names)

    def test_operations_observer_does_not_subscribe_projection_invalidation(self) -> None:
        names = set(operations_observer_event_names(build_event_definition_registry()))

        self.assertNotIn(OPERATIONS_PROJECTION_INVALIDATED_EVENT, names)

    def test_operations_observer_runs_maintenance_after_processing_events(self) -> None:
        events = EventsApplicationService(InMemoryEventsBackend())
        topic = named_event_topic("operations.maintenance.test")
        events.publish(
            Event(
                name="operations.maintenance.test",
                topic=topic,
                kind="fact",
                payload={"event_name": "operations.maintenance.test"},
            ),
        )
        handled: list[str] = []
        maintenance_calls: list[str] = []
        runtime = OperationsObserverRuntimeService(
            events_service=events,
            maintenance_handler=lambda: maintenance_calls.append("maintenance"),
        )
        runtime.subscribe_topic(
            topic,
            subscription_id="operations.maintenance.test",
            handler=lambda record: handled.append(record.cursor),
        )

        processed = runtime.run_until_stopped(
            worker_id="maintenance-test",
            poll_interval_seconds=0.01,
            max_events=1,
        )

        self.assertEqual(processed, 1)
        self.assertEqual(len(handled), 1)
        self.assertGreaterEqual(len(maintenance_calls), 1)

    def test_operations_observer_can_start_new_subscription_at_topic_tail(self) -> None:
        events = EventsApplicationService(InMemoryEventsBackend())
        topic = named_event_topic("operations.tail.test")
        events.publish(
            Event(
                name="operations.tail.test",
                topic=topic,
                kind="fact",
                payload={"event_name": "operations.tail.test", "value": "old"},
            ),
        )
        handled: list[str] = []
        runtime = OperationsObserverRuntimeService(
            events_service=events,
            start_at_tail_when_no_cursor=True,
        )
        runtime.subscribe_topic(
            topic,
            subscription_id="operations.tail.test",
            handler=lambda record: handled.append(record.envelope.payload["value"]),
        )

        self.assertEqual(runtime.process_available_events(), 0)
        events.publish(
            Event(
                name="operations.tail.test",
                topic=topic,
                kind="fact",
                payload={"event_name": "operations.tail.test", "value": "new"},
            ),
        )

        self.assertEqual(runtime.process_available_events(), 1)
        self.assertEqual(handled, ["new"])

    def test_operations_state_projection_maintenance_covers_all_modules(self) -> None:
        self.assertEqual(
            OPERATIONS_STATE_PROJECTION_MODULES,
            OPERATIONS_PROJECTION_MODULES,
        )
        self.assertIn("browser", OPERATIONS_STATE_PROJECTION_MODULES)

    def test_events_operations_health_treats_stuck_consumers_as_warning(self) -> None:
        health = events_operations_health(
            events_service_available=True,
            stuck_count=2,
            lagging_count=2,
            dead_letter_count=0,
            uncovered_topic_count=0,
        )

        self.assertEqual(health, "warning")

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

    def test_memory_materializer_stores_file_details_outside_page_projection(
        self,
    ) -> None:
        store = self._projection_store()
        store.record_projection(
            module="memory",
            kind="memory_file_detail",
            query_key="stale-memory-file",
            payload={"file_id": "stale-memory-file", "excerpt": "old"},
        )
        store.record_projection(
            module="memory",
            kind="memory_space_detail",
            query_key="stale-memory-space",
            payload={"space_id": "stale-memory-space"},
        )
        materializer = OperationsProjectionMaterializer(
            source_provider=_FakeOperationsSourceProvider(),
            projection_store=store,
        )

        materialized = materializer.materialize_modules(("memory",))

        self.assertEqual(materialized, 1)
        page_projection = store.get_projection(module="memory", kind="page")
        self.assertIsNotNone(page_projection)
        assert page_projection is not None
        self.assertEqual(page_projection.payload["file_details"], [])
        detail = store.get_projection(
            module="memory",
            kind="memory_file_detail",
            query_key="assistant:MEMORY.md",
        )
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail.payload["excerpt"], "hello")
        self.assertIsNone(
            store.get_projection(
                module="memory",
                kind="memory_file_detail",
                query_key="stale-memory-file",
            ),
        )
        space_detail = store.get_projection(
            module="memory",
            kind="memory_space_detail",
            query_key="assistant",
        )
        self.assertIsNotNone(space_detail)
        assert space_detail is not None
        self.assertEqual(space_detail.payload["space_id"], "assistant")
        self.assertEqual(space_detail.payload["agents"], ["assistant"])
        self.assertIsNone(
            store.get_projection(
                module="memory",
                kind="memory_space_detail",
                query_key="stale-memory-space",
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
            executor_lease_query=_FakeOrchestrationExecutorControl(
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

    def test_materializer_maps_skill_events_to_skills_and_events_projections(
        self,
    ) -> None:
        store = self._projection_store()
        materializer = OperationsProjectionMaterializer(
            source_provider=_FakeOperationsSourceProvider(),
            projection_store=store,
        )

        materialized = materializer.materialize_observed_modules(("skills",))

        self.assertEqual(materialized, 2)
        skills_page = store.get_projection(module="skills", kind="page")
        events_page = store.get_projection(module="events", kind="page")
        self.assertIsNotNone(skills_page)
        self.assertIsNotNone(events_page)
        assert skills_page is not None
        assert events_page is not None
        self.assertEqual(skills_page.payload["module"], "skills")
        self.assertEqual(events_page.payload["module"], "events")

    def test_materializer_maps_browser_events_to_browser_daemon_and_events(
        self,
    ) -> None:
        store = self._projection_store()
        materializer = OperationsProjectionMaterializer(
            source_provider=_FakeOperationsSourceProvider(),
            projection_store=store,
        )

        materialized = materializer.materialize_observed_modules(("browser",))

        self.assertEqual(materialized, 3)
        browser_page = store.get_projection(module="browser", kind="page")
        daemon_page = store.get_projection(module="daemon", kind="page")
        events_page = store.get_projection(module="events", kind="page")
        self.assertIsNotNone(browser_page)
        self.assertIsNotNone(daemon_page)
        self.assertIsNotNone(events_page)
        assert browser_page is not None
        assert daemon_page is not None
        assert events_page is not None
        self.assertEqual(browser_page.payload["module"], "browser")
        self.assertEqual(daemon_page.payload["module"], "daemon")
        self.assertEqual(events_page.payload["module"], "events")

    def test_observer_runtime_runs_maintenance_before_idle_wait(self) -> None:
        events_service = EventsApplicationService(InMemoryEventsBackend())
        maintenance_calls: list[str] = []
        runtime = OperationsObserverRuntimeService(
            events_service=events_service,
            maintenance_handler=lambda: maintenance_calls.append("flush"),
        )

        processed = runtime.run_until_stopped(
            worker_id="operations-observer-test",
            poll_interval_seconds=0.05,
            max_idle_cycles=1,
        )

        self.assertEqual(processed, 0)
        self.assertEqual(maintenance_calls, ["flush"])

    def test_observer_runtime_direct_processing_keeps_full_scan_semantics(self) -> None:
        events_service = EventsApplicationService(InMemoryEventsBackend())
        observed: list[str] = []
        runtime = OperationsObserverRuntimeService(events_service=events_service)
        runtime.subscribe_event_name(
            "tool.worker.stale",
            subscription_id="operations.observer.tool.worker.stale.test",
            handler=lambda record: observed.append(record.envelope.id),
        )

        events_service.publish(Event(name="tool.worker.stale", payload={"worker_id": "w1"}))
        first_processed = runtime.process_available_events()
        events_service.publish(Event(name="tool.worker.stale", payload={"worker_id": "w2"}))
        second_processed = runtime.process_available_events()

        self.assertEqual(first_processed, 1)
        self.assertEqual(second_processed, 1)
        self.assertEqual(len(observed), 2)

    def test_observer_runtime_event_driven_wakeup_does_not_scan_all_topics(self) -> None:
        events_service = EventsApplicationService(InMemoryEventsBackend())
        observed: list[str] = []
        runtime = OperationsObserverRuntimeService(events_service=events_service)
        runtime.subscribe_event_name(
            "tool.run.succeeded",
            subscription_id="operations.observer.tool.run.succeeded.test",
            handler=lambda record: observed.append(record.envelope.event_name),
        )
        runtime.subscribe_event_name(
            "llm.invocation_succeeded",
            subscription_id="operations.observer.llm.invocation_succeeded.test",
            handler=lambda record: observed.append(record.envelope.event_name),
        )
        events_service.publish(Event(name="tool.run.succeeded", payload={"run_id": "tool-1"}))
        events_service.publish(Event(name="llm.invocation_succeeded", payload={"id": "llm-1"}))
        runtime._wakeup_topics.add(named_event_topic("tool.run.succeeded"))

        processed = runtime.process_available_events(event_driven=True)

        self.assertEqual(processed, 1)
        self.assertEqual(observed, ["tool.run.succeeded"])

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

    def test_operations_observer_static_events_include_skill_events(self) -> None:
        event_names = operations_observer_event_names()

        self.assertIn("skills.readiness.changed", event_names)
        for event_name in SKILL_OPERATION_EVENT_NAMES:
            self.assertIn(event_name, event_names)

    def test_operations_observer_static_events_include_access_events(self) -> None:
        event_names = operations_observer_event_names()

        for event_name in ACCESS_OPERATION_EVENT_NAMES:
            self.assertIn(event_name, event_names)

    def test_operations_observer_static_events_include_memory_events(self) -> None:
        event_names = operations_observer_event_names()

        for event_name in MEMORY_OPERATION_EVENT_NAMES:
            self.assertIn(event_name, event_names)

    def test_operations_observer_static_events_include_browser_events(self) -> None:
        event_names = operations_observer_event_names()

        self.assertIn("browser.network.fetch.executed", event_names)
        self.assertIn("browser.network.replay.executed", event_names)
        for event_name in BROWSER_OPERATION_EVENT_NAMES:
            self.assertIn(event_name, event_names)

    def test_memory_operations_write_flush_uses_remember_events(self) -> None:
        event = OperationsObservedEvent(
            id="event-memory-remember-1",
            cursor="1",
            topic="events.named.memory.remember.succeeded",
            event_name="memory.remember.succeeded",
            module="memory",
            owner="memory",
            kind="observe",
            level="info",
            status="succeeded",
            entity_id="memory/2026-05-22.md",
            run_id="run-1",
            trace_id="trace-1",
            source_event_name=None,
            occurred_at=datetime(2026, 5, 22, 8, 0, tzinfo=timezone.utc),
            payload={
                "space_id": "assistant",
                "path": "memory/2026-05-22.md",
                "operation": "append_daily",
            },
        )
        observation = OperationsModuleObservation(
            module="memory",
            owner="memory",
            recent_events=(event,),
        )
        provider = MemoryOperationsReadModelProvider(
            agent_service=None,
            memory_query_service=None,
            operations_observation=_ModuleOnlyOperationsObservation(
                observation,
                module="memory",
            ),
        )

        page = provider.page()

        self.assertEqual(page.write_flush.total, 1)
        self.assertEqual(page.write_flush.rows[0].cells["operation"], "remember.succeeded")

    def test_access_operations_auth_success_rate_uses_resolution_events(self) -> None:
        timestamp = datetime(2026, 5, 21, 8, 7, tzinfo=timezone.utc)
        observation = OperationsModuleObservation(
            module="access",
            owner="access",
            recent_events=(
                OperationsObservedEvent(
                    id="access-success-1",
                    cursor="access-success-1",
                    topic=f"events.named.{ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT}",
                    event_name=ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT,
                    module="access",
                    owner="access",
                    kind="fact",
                    level="info",
                    status="succeeded",
                    entity_id="openai-api-key",
                    run_id="run-access-1",
                    trace_id="trace-access-1",
                    source_event_name=None,
                    occurred_at=timestamp,
                    payload={"target_id": "openai-api-key"},
                ),
                OperationsObservedEvent(
                    id="access-success-2",
                    cursor="access-success-2",
                    topic=f"events.named.{ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT}",
                    event_name=ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT,
                    module="access",
                    owner="access",
                    kind="fact",
                    level="info",
                    status="succeeded",
                    entity_id="openai-api-key",
                    run_id="run-access-2",
                    trace_id="trace-access-2",
                    source_event_name=None,
                    occurred_at=timestamp + timedelta(seconds=1),
                    payload={"target_id": "openai-api-key"},
                ),
                OperationsObservedEvent(
                    id="access-failed-1",
                    cursor="access-failed-1",
                    topic=f"events.named.{ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT}",
                    event_name=ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT,
                    module="access",
                    owner="access",
                    kind="fact",
                    level="error",
                    status="failed",
                    entity_id="missing-api-key",
                    run_id="run-access-3",
                    trace_id="trace-access-3",
                    source_event_name=None,
                    occurred_at=timestamp + timedelta(seconds=2),
                    payload={"target_id": "missing-api-key", "reason": "missing"},
                ),
            ),
        )
        provider = AccessOperationsReadModelProvider(
            access_service=None,
            access_governance_repository=None,
            llm_service=None,
            tool_service=None,
            channel_profile_service=None,
            lark_channel_runtime_service=None,
            web_channel_runtime_service=None,
            webhook_channel_runtime_service=None,
            operations_observation=_ModuleOnlyOperationsObservation(
                observation,
                module="access",
            ),
        )

        page = provider.page()

        self.assertEqual(page.auth_success_rate.title, "Credential Resolve Success")
        self.assertEqual(page.auth_success_rate.total, 3)
        segments = {segment.id: segment.value for segment in page.auth_success_rate.segments}
        self.assertEqual(segments, {"succeeded": 2, "failed": 1})
        self.assertEqual(page.access_audit_summary.total, 3)

    def test_access_operations_prefers_persisted_event_buckets_for_24h_counts(
        self,
    ) -> None:
        timestamp = datetime.now(timezone.utc)
        observation = OperationsModuleObservation(
            module="access",
            owner="access",
            recent_events=(
                OperationsObservedEvent(
                    id="access-success-recent",
                    cursor="access-success-recent",
                    topic=f"events.named.{ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT}",
                    event_name=ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT,
                    module="access",
                    owner="access",
                    kind="fact",
                    level="info",
                    status="succeeded",
                    entity_id="openai-api-key",
                    run_id=None,
                    trace_id=None,
                    source_event_name=None,
                    occurred_at=timestamp,
                    payload={"target_id": "openai-api-key"},
                ),
            ),
        )
        buckets: tuple[dict[str, object], ...] = (
            {
                "module": "access",
                "owner": "access",
                "event_name": ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT,
                "status": "succeeded",
                "level": "info",
                "bucket_start": timestamp.replace(minute=0, second=0, microsecond=0),
                "count": 5,
                "updated_at": timestamp,
            },
            {
                "module": "access",
                "owner": "access",
                "event_name": ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT,
                "status": "failed",
                "level": "error",
                "bucket_start": timestamp.replace(minute=0, second=0, microsecond=0),
                "count": 2,
                "updated_at": timestamp,
            },
        )
        provider = AccessOperationsReadModelProvider(
            access_service=None,
            access_governance_repository=None,
            llm_service=None,
            tool_service=None,
            channel_profile_service=None,
            lark_channel_runtime_service=None,
            web_channel_runtime_service=None,
            webhook_channel_runtime_service=None,
            operations_observation=_ModuleOnlyOperationsObservation(
                observation,
                module="access",
                event_buckets=buckets,
            ),
        )

        page = provider.page()

        segments = {segment.id: segment.value for segment in page.auth_success_rate.segments}
        metrics = {metric.id: metric for metric in page.metrics}
        self.assertEqual(page.auth_success_rate.total, 7)
        self.assertEqual(segments, {"succeeded": 5, "failed": 2})
        self.assertEqual(metrics["failed_auth"].value, "2")

    def test_events_operations_uses_observation_snapshot_and_buckets(
        self,
    ) -> None:
        timestamp = datetime.now(timezone.utc)
        observed = OperationsObservedEvent(
            id="tool-failed-1",
            cursor="tool-failed-1",
            topic="events.named.tool.run.failed",
            event_name="tool.run.failed",
            module="tool",
            owner="tool",
            kind="fact",
            level="error",
            status="failed",
            entity_id="tool-run-1",
            run_id="run-1",
            trace_id="trace-1",
            source_event_name=None,
            occurred_at=timestamp,
            payload={"tool_id": "openai_image_generate"},
        )
        observation = OperationsModuleObservation(
            module="tool",
            owner="tool",
            recent_events=(observed,),
        )
        buckets: tuple[dict[str, object], ...] = (
            {
                "module": "tool",
                "owner": "tool",
                "event_name": "tool.run.failed",
                "status": "failed",
                "level": "error",
                "bucket_start": timestamp.replace(minute=0, second=0, microsecond=0),
                "count": 3,
                "updated_at": timestamp,
            },
            {
                "module": "access",
                "owner": "access",
                "event_name": ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT,
                "status": "succeeded",
                "level": "info",
                "bucket_start": timestamp.replace(minute=0, second=0, microsecond=0),
                "count": 4,
                "updated_at": timestamp,
            },
        )
        provider = EventsOperationsReadModelProvider(
            events_service=None,
            operations_observation=_ModuleOnlyOperationsObservation(
                observation,
                module="tool",
                event_buckets=buckets,
            ),
        )

        page = provider.page()

        self.assertEqual(page.recent_events.total, 1)
        self.assertEqual(page.events_over_time.title, "Events by Status (24h)")
        self.assertEqual(page.events_over_time.total, 7)
        status_segments = {
            segment.id: segment.value for segment in page.events_over_time.segments
        }
        self.assertEqual(status_segments, {"succeeded": 4, "failed": 3})
        owner_segments = {
            segment.id: segment.value for segment in page.events_by_surface.segments
        }
        self.assertEqual(owner_segments, {"access": 4, "tool": 3})

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

    def test_skills_operations_uses_readiness_changed_events(self) -> None:
        package = SkillPackage(
            manifest=SkillManifest(
                api_version="skills.crxzipple/v1alpha1",
                kind="Skill",
                name="repo-review",
                description="Review repository changes.",
                required_tools=("git_diff",),
                required_effects=("network",),
            ),
            root_path="/skills/repo-review",
            manifest_path="/skills/repo-review/SKILL.md",
            instructions_path="/skills/repo-review/SKILL.md",
            source="system",
        )

        class _SkillManager:
            def list_available(self, *, workspace_dir, surface):
                del workspace_dir, surface
                return (package,)

        event = OperationsObservedEvent(
            id="event-skill-ready-1",
            cursor="1",
            topic="events.named.skills.readiness.changed",
            event_name="skills.readiness.changed",
            module="skills",
            owner="skills",
            kind="observe",
            level="warning",
            status="setup_needed",
            entity_id="repo-review",
            run_id="run-1",
            trace_id=None,
            source_event_name=None,
            occurred_at=datetime(2026, 5, 21, 8, 0, tzinfo=timezone.utc),
            payload={
                "skill": "repo-review",
                "status": "setup_needed",
                "missing_tools": ["git_diff"],
                "missing_effects": ["network"],
            },
        )
        observation = OperationsModuleObservation(
            module="skills",
            owner="skills",
            recent_events=(event,),
        )
        provider = SkillsOperationsReadModelProvider(
            skill_manager=_SkillManager(),
            operations_observation=_ModuleOnlyOperationsObservation(
                observation,
                module="skills",
            ),
        )

        page = provider.page()

        self.assertEqual(page.recently_resolved_skills.rows[0].status, "Setup Needed")
        missing_rows = {
            row.cells["required"]: row.cells["type"]
            for row in page.missing_capabilities.rows
        }
        self.assertEqual(missing_rows["git_diff"], "Tool")
        self.assertEqual(missing_rows["network"], "Authorization Effect")

    def test_skills_operations_reads_declared_skill_topics_without_bus_scan(self) -> None:
        package = SkillPackage(
            manifest=SkillManifest(
                api_version="skills.crxzipple/v1alpha1",
                kind="Skill",
                name="repo-review",
                description="Review repository changes.",
            ),
            root_path="/skills/repo-review",
            manifest_path="/skills/repo-review/SKILL.md",
            instructions_path="/skills/repo-review/SKILL.md",
            source="system",
        )
        timestamp = datetime(2026, 5, 21, 8, 5, tzinfo=timezone.utc)
        read_topic = named_event_topic("skills.read.succeeded")

        class _SkillManager:
            def list_available(self, *, workspace_dir, surface):
                del workspace_dir, surface
                return (package,)

        class _EventsService:
            def __init__(self) -> None:
                self.read_topics: list[str] = []

            def list_event_topics(self):
                raise AssertionError("Skills operations should not scan the event bus.")

            def read_recent_event_topic(self, topic, *, limit):
                self.read_topics.append(topic)
                if topic != read_topic:
                    return ()
                return (
                    EventTopicRecord(
                        cursor="skill-read-1",
                        envelope=Event(
                            name="skills.read.succeeded",
                            payload={
                                "skill": "repo-review",
                                "status": "succeeded",
                                "path": "SKILL.md",
                                "duration_ms": 37.5,
                            },
                            occurred_at=timestamp,
                        ),
                    ),
                )

        events_service = _EventsService()
        provider = SkillsOperationsReadModelProvider(
            skill_manager=_SkillManager(),
            events_service=events_service,
        )

        page = provider.page()

        self.assertIn(
            read_topic,
            events_service.read_topics,
        )
        self.assertEqual(
            set(events_service.read_topics),
            {named_event_topic(event_name) for event_name in SKILL_OPERATION_EVENT_NAMES},
        )
        self.assertEqual(page.resolution_logs.total, 1)
        self.assertEqual(page.resolution_logs.rows[0].cells["event"], "read.succeeded")
        self.assertEqual(page.skill_reads.total, 1)
        self.assertEqual(page.skill_reads.rows[0].cells["skill"], "repo-review")
        self.assertEqual(page.skill_reads.rows[0].cells["duration"], "38 ms")
        self.assertEqual(page.top_used_skills.total, 1)
        self.assertEqual(page.top_used_skills.rows[0].cells["skill"], "repo-review")
        self.assertEqual(page.top_used_skills.rows[0].cells["reads"], "1")

    def test_skills_operations_top_used_is_runtime_usage_from_events(self) -> None:
        timestamp = datetime(2026, 5, 21, 8, 8, tzinfo=timezone.utc)
        package = SkillPackage(
            manifest=SkillManifest(
                api_version="skills.crxzipple/v1alpha1",
                kind="Skill",
                name="repo-review",
                description="Review repository changes.",
            ),
            root_path="/skills/repo-review",
            manifest_path="/skills/repo-review/SKILL.md",
            instructions_path="/skills/repo-review/SKILL.md",
            source="system",
        )

        class _SkillManager:
            def list_available(self, *, workspace_dir, surface):
                del workspace_dir, surface
                return (package,)

        observation = OperationsModuleObservation(
            module="skills",
            owner="skills",
            recent_events=(
                OperationsObservedEvent(
                    id="skill-resolution-1",
                    cursor="skill-resolution-1",
                    topic=f"events.named.{SKILL_RESOLUTION_COMPLETED_EVENT}",
                    event_name=SKILL_RESOLUTION_COMPLETED_EVENT,
                    module="skills",
                    owner="skills",
                    kind="observe",
                    level="info",
                    status="ready",
                    entity_id="run-usage-1",
                    run_id="run-usage-1",
                    trace_id=None,
                    source_event_name=None,
                    occurred_at=timestamp,
                    payload={
                        "run_id": "run-usage-1",
                        "surface": "interactive",
                        "skills": [{"skill": "repo-review", "status": "ready"}],
                    },
                ),
                OperationsObservedEvent(
                    id="skill-read-1",
                    cursor="skill-read-1",
                    topic=f"events.named.{SKILL_READ_SUCCEEDED_EVENT}",
                    event_name=SKILL_READ_SUCCEEDED_EVENT,
                    module="skills",
                    owner="skills",
                    kind="observe",
                    level="info",
                    status="succeeded",
                    entity_id="repo-review",
                    run_id="run-usage-1",
                    trace_id=None,
                    source_event_name=None,
                    occurred_at=timestamp + timedelta(seconds=1),
                    payload={
                        "skill": "repo-review",
                        "surface": "interactive",
                        "duration_ms": 12,
                    },
                ),
            ),
        )
        provider = SkillsOperationsReadModelProvider(
            skill_manager=_SkillManager(),
            operations_observation=_ModuleOnlyOperationsObservation(
                observation,
                module="skills",
            ),
        )

        page = provider.page()

        self.assertEqual(page.top_used_skills.title, "Runtime Skill Usage")
        self.assertEqual(page.top_used_skills.total, 1)
        row = page.top_used_skills.rows[0]
        self.assertEqual(row.cells["skill"], "repo-review")
        self.assertEqual(row.cells["resolved"], "1")
        self.assertEqual(row.cells["reads"], "1")
        self.assertEqual(row.cells["surface"], "interactive")

    def test_skills_operations_projects_authoring_backlog_and_failures(self) -> None:
        timestamp = datetime(2026, 5, 21, 8, 10, tzinfo=timezone.utc)
        failed_event = OperationsObservedEvent(
            id="skill-draft-failed-1",
            cursor="draft-3",
            topic=f"events.named.{SKILL_DRAFT_APPLY_FAILED_EVENT}",
            event_name=SKILL_DRAFT_APPLY_FAILED_EVENT,
            module="skills",
            owner="skills",
            kind="observe",
            level="error",
            status="failed",
            entity_id="skill-draft:repo-review",
            run_id="run-authoring-1",
            trace_id=None,
            source_event_name=None,
            occurred_at=timestamp + timedelta(seconds=2),
            payload={
                "draft_id": "skill-draft:repo-review",
                "draft_status": "invalid",
                "intent": "create",
                "skill": "repo-review",
                "actor": "assistant",
                "validation_error_count": 1,
                "validation_warning_count": 0,
                "validation_errors": ["required tool git_diff is unavailable"],
                "error_message": "Skill draft is invalid.",
            },
        )
        applied_event = OperationsObservedEvent(
            id="skill-draft-applied-1",
            cursor="draft-4",
            topic=f"events.named.{SKILL_DRAFT_APPLIED_EVENT}",
            event_name=SKILL_DRAFT_APPLIED_EVENT,
            module="skills",
            owner="skills",
            kind="observe",
            level="info",
            status="applied",
            entity_id="skill-draft:done",
            run_id="run-authoring-2",
            trace_id=None,
            source_event_name=None,
            occurred_at=timestamp + timedelta(seconds=3),
            payload={
                "draft_id": "skill-draft:done",
                "draft_status": "applied",
                "intent": "create",
                "skill": "done-skill",
                "actor": "assistant",
            },
        )
        observation = OperationsModuleObservation(
            module="skills",
            owner="skills",
            recent_events=(
                OperationsObservedEvent(
                    id="skill-draft-created-1",
                    cursor="draft-1",
                    topic=f"events.named.{SKILL_DRAFT_CREATED_EVENT}",
                    event_name=SKILL_DRAFT_CREATED_EVENT,
                    module="skills",
                    owner="skills",
                    kind="observe",
                    level="info",
                    status="draft",
                    entity_id="skill-draft:repo-review",
                    run_id="run-authoring-1",
                    trace_id=None,
                    source_event_name=None,
                    occurred_at=timestamp,
                    payload={
                        "draft_id": "skill-draft:repo-review",
                        "draft_status": "draft",
                        "intent": "create",
                        "skill": "repo-review",
                        "actor": "assistant",
                    },
                ),
                OperationsObservedEvent(
                    id="skill-draft-validated-1",
                    cursor="draft-2",
                    topic=f"events.named.{SKILL_DRAFT_VALIDATED_EVENT}",
                    event_name=SKILL_DRAFT_VALIDATED_EVENT,
                    module="skills",
                    owner="skills",
                    kind="observe",
                    level="info",
                    status="validated",
                    entity_id="skill-draft:repo-review",
                    run_id="run-authoring-1",
                    trace_id=None,
                    source_event_name=None,
                    occurred_at=timestamp + timedelta(seconds=1),
                    payload={
                        "draft_id": "skill-draft:repo-review",
                        "draft_status": "validated",
                        "intent": "create",
                        "skill": "repo-review",
                        "actor": "assistant",
                        "readiness_status": "ready",
                    },
                ),
                failed_event,
                applied_event,
            ),
        )
        provider = SkillsOperationsReadModelProvider(
            skill_manager=None,
            operations_observation=_ModuleOnlyOperationsObservation(
                observation,
                module="skills",
            ),
        )

        page = provider.page()

        self.assertEqual(page.authoring_backlog.total, 1)
        self.assertEqual(page.authoring_backlog.rows[0].cells["draft"], "skill-draft:repo-review")
        self.assertEqual(page.authoring_backlog.rows[0].cells["status"], "Invalid")
        self.assertEqual(page.authoring_backlog.rows[0].cells["next_step"], "Review failure and revise draft")
        self.assertEqual(page.authoring_failures.total, 1)
        self.assertEqual(page.authoring_failures.rows[0].cells["skill"], "repo-review")
        self.assertIn(
            "required tool git_diff",
            page.authoring_failures.rows[0].cells["error"],
        )

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
    def __init__(
        self,
        module_observation: OperationsModuleObservation,
        *,
        module: str = "orchestration",
        event_buckets: tuple[dict[str, object], ...] = (),
    ) -> None:
        self._module_observation = module_observation
        self._module = module
        self._event_buckets = event_buckets

    def get_module_observation(
        self,
        module: str,
    ) -> OperationsModuleObservation | None:
        return self._module_observation if module == self._module else None

    def snapshot(self) -> OperationsObservationSnapshot:
        return OperationsObservationSnapshot(
            version=4,
            updated_at=self._module_observation.updated_at,
            modules=(self._module_observation,),
        )

    def list_event_buckets(
        self,
        *,
        module: str | None = None,
        event_name: str | None = None,
        since: datetime | None = None,
        limit: int = 500,
    ) -> tuple[dict[str, object], ...]:
        del since
        rows = tuple(
            bucket
            for bucket in self._event_buckets
            if (module is None or bucket.get("module") == module)
            and (event_name is None or bucket.get("event_name") == event_name)
        )
        return rows[:limit]


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

    def memory_page(self, query: object | None = None) -> dict[str, object]:
        del query
        return {
            "module": "memory",
            "title": "Memory",
            "source_files": {
                "id": "source_files",
                "title": "Source Files",
                "columns": [],
                "rows": [
                    {
                        "id": "assistant:MEMORY.md",
                        "cells": {"file": "MEMORY.md"},
                    }
                ],
                "total": 1,
            },
            "memory_stores": {
                "id": "memory_stores",
                "title": "Memory Stores",
                "columns": [],
                "rows": [
                    {
                        "id": "assistant",
                        "cells": {
                            "agent": "assistant",
                            "space_id": "assistant",
                            "status": "Ready",
                            "files": "1",
                            "indexed_files": "1",
                        },
                        "status": "Ready",
                        "tone": "success",
                    }
                ],
                "total": 1,
            },
            "file_details": [
                {
                    "file_id": "assistant:MEMORY.md",
                    "title": "MEMORY.md",
                    "status": "Indexed",
                    "tone": "success",
                    "summary": [],
                    "excerpt": "hello",
                    "related": {
                        "id": "related",
                        "title": "Related",
                        "columns": [],
                        "rows": [],
                        "total": 0,
                    },
                    "raw_payload": {"file": {"path": "MEMORY.md"}},
                }
            ],
        }

    def skills_page(self, query: object | None = None) -> dict[str, object]:
        del query
        return {"module": "skills", "title": "Skills Runtime"}

    def browser_page(self, query: object | None = None) -> dict[str, object]:
        del query
        return {
            "module": "browser",
            "title": "Browser Runtime",
            "profiles": {"id": "profiles", "rows": [], "total": 0},
            "profile_pools": {"id": "profile_pools", "rows": [], "total": 0},
            "profile_allocations": {
                "id": "profile_allocations",
                "rows": [],
                "total": 0,
            },
        }

    def events_page(self, query: object | None = None) -> dict[str, object]:
        del query
        return {"module": "events", "title": "Events Runtime"}

    def daemon_page(self, query: object | None = None) -> dict[str, object]:
        del query
        return {"module": "daemon", "title": "Daemon Runtime"}

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

    def memory_page(self, query: object | None = None) -> dict[str, object]:
        del query
        return {
            "module": "memory",
            "title": "Memory",
            "source_files": {
                "id": "source_files",
                "title": "Source Files",
                "columns": [],
                "rows": [],
                "total": 0,
            },
            "file_details": [],
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
