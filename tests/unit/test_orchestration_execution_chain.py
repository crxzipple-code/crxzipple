from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from crxzipple.core.db import Base
from crxzipple.modules.orchestration.domain import (
    ExecutionChain,
    ExecutionChainStatus,
    ExecutionOwnerKind,
    ExecutionOwnerReference,
    ExecutionStep,
    ExecutionStepItem,
    ExecutionStepItemKind,
    ExecutionStepItemStatus,
    ExecutionStepKind,
    ExecutionStepStatus,
    InboundInstruction,
    OrchestrationQueuePolicy,
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    OrchestrationValidationError,
    PendingApprovalRequest,
)
from crxzipple.modules.orchestration.application.commands import (
    AdvanceAssignmentInput,
    CompleteAssignmentInput,
    ResumeOrchestrationRunInput,
    SubmitOrchestrationTurnInput,
)
from crxzipple.modules.orchestration.application.coordinators.ingress import (
    RunIngressCoordinator,
)
from crxzipple.modules.orchestration.application.coordinators.intake import (
    RunIntakeCoordinator,
)
from crxzipple.modules.orchestration.application.coordinators.progress import (
    RunProgressCoordinator,
)
from crxzipple.modules.orchestration.application.coordinators.waiting import (
    RunWaitCoordinator,
)
from crxzipple.modules.orchestration.application.event_contracts import (
    ORCHESTRATION_ORPHAN_TOOL_RESULT_OBSERVED_EVENT,
)
from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_DISPATCH_OWNER_KINDS,
    ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
)
from crxzipple.modules.orchestration.application.execution_chain_lifecycle import (
    ORCHESTRATION_RUN_INTAKE_OWNER_KIND,
    cancel_active_execution_step,
    fail_active_execution_step,
    mark_approval_request_step_item_terminal,
    mark_tool_run_step_item_terminal,
    materialize_approval_execution_step,
    materialize_resume_execution_step,
    materialize_tool_batch_execution_step,
    materialize_tool_result_session_item_items,
)
from crxzipple.modules.orchestration.application.engine import EngineAdvanceOutcome
from crxzipple.modules.orchestration.application.execution import RunExecutionService
from crxzipple.modules.orchestration.application.tool_resume import (
    OrchestrationToolResumeCoordinator,
)
from crxzipple.modules.orchestration.application.engine_session_recorder import (
    OrchestrationSessionRecorder,
)
from crxzipple.modules.orchestration.application.intake_commands import (
    AcceptOrchestrationRunInput,
    EnqueueOrchestrationRunInput,
)
from crxzipple.modules.orchestration.application.query import (
    OrchestrationRunQueryService,
)
from crxzipple.modules.orchestration.application.scheduler import OrchestrationScheduler
from crxzipple.modules.orchestration.infrastructure.adapters.dispatch import (
    OrchestrationDispatchAdapter,
)
from crxzipple.modules.orchestration.infrastructure.persistence import (
    SqlAlchemyExecutionChainRepository,
    SqlAlchemyExecutionStepItemRepository,
    SqlAlchemyExecutionStepRepository,
)
from crxzipple.modules.session.application import ListSessionItemsInput
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionItem,
    SessionItemKind,
    SessionItemVisibility,
    SessionRouteContext,
)
from crxzipple.modules.tool.domain import (
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolRunResult,
)
from crxzipple.shared.content_blocks import text_content_block
from crxzipple.shared.domain.events import Event
from crxzipple.shared.infrastructure.sqlalchemy_uow import SqlAlchemyUnitOfWork


class _FakeSessionRecorderPort:
    def __init__(self) -> None:
        self.messages: list[SimpleNamespace] = []
        self.items: list[SimpleNamespace] = []

    def get_message_by_source(
        self,
        *,
        session_key: str,
        session_id: str,
        source_kind: str,
        source_id: str,
    ) -> SimpleNamespace | None:
        for message in self.messages:
            if (
                message.session_key == session_key
                and message.session_id == session_id
                and message.source_kind == source_kind
                and message.source_id == source_id
            ):
                return message
        return None

    def get_item_by_source(self, data: object) -> SimpleNamespace | None:
        for item in self.items:
            if (
                item.session_key == getattr(data, "session_key")
                and item.session_id == getattr(data, "session_id")
                and item.source_module == getattr(data, "source_module")
                and item.source_kind == getattr(data, "source_kind")
                and item.source_id == getattr(data, "source_id")
            ):
                return item
        return None

    def append_message(self, data: object) -> SimpleNamespace:
        message = SimpleNamespace(
            id=f"message-{len(self.messages) + 1}",
            session_key=getattr(data, "session_key"),
            session_id=getattr(data, "session_id"),
            role=getattr(data, "role"),
            kind=getattr(data, "kind", None),
            content_payload=getattr(data, "content_payload"),
            source_kind=getattr(data, "source_kind"),
            source_id=getattr(data, "source_id"),
            metadata=dict(getattr(data, "metadata", {}) or {}),
        )
        self.messages.append(message)
        return message

    def append_messages(self, data: object) -> tuple[SimpleNamespace, ...]:
        return tuple(
            self.append_message(message)
            for message in getattr(data, "messages")
        )

    def append_items(self, data: object) -> tuple[SimpleNamespace, ...]:
        items: list[SimpleNamespace] = []
        for item_input in getattr(data, "items"):
            item = SimpleNamespace(
                id=f"item-{len(self.items) + 1}",
                session_key=getattr(item_input, "session_key"),
                session_id=getattr(item_input, "session_id"),
                role=getattr(item_input, "role"),
                kind=getattr(item_input, "kind"),
                content_payload=getattr(item_input, "content_payload"),
                source_module=getattr(item_input, "source_module"),
                source_kind=getattr(item_input, "source_kind"),
                source_id=getattr(item_input, "source_id"),
                call_id=getattr(item_input, "call_id"),
                tool_name=getattr(item_input, "tool_name"),
                metadata=dict(getattr(item_input, "metadata", {}) or {}),
            )
            self.items.append(item)
            items.append(item)
        return tuple(items)


class _FakeSessionItemLookupPort:
    def __init__(self, items: tuple[SessionItem, ...]) -> None:
        self.items = items
        self.item_inputs: list[ListSessionItemsInput] = []
        self.message_reads = 0

    def list_model_visible_items(
        self,
        data: ListSessionItemsInput,
    ) -> list[SessionItem]:
        self.item_inputs.append(data)
        return list(self.items)

    def list_messages(self, _data: object) -> list[object]:
        self.message_reads += 1
        return []


class _FakeEventPublisher:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def publish(self, event: Event) -> None:
        self.events.append(event)


class _FakeToolExecutionPort:
    def __init__(self, tool_run: ToolRun) -> None:
        self.tool_run = tool_run

    def get_tool_run(self, run_id: str) -> ToolRun:
        assert run_id == self.tool_run.id
        return self.tool_run


class _FakeBackgroundToolResumeEngine:
    def __init__(self, tool_run: ToolRun) -> None:
        self.tool_execution_port = _FakeToolExecutionPort(tool_run)
        self.appended_run_ids: list[str] = []

    def append_completed_background_tool_results(
        self,
        run: OrchestrationRun,
        *,
        tool_runs: tuple[object, ...],
    ) -> tuple[str, ...]:
        self.appended_run_ids.append(run.id)
        return tuple(f"message-{index + 1}" for index, _ in enumerate(tool_runs))


def _create_sqlite_engine_with_foreign_keys():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _set_foreign_keys(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return engine


def test_orchestration_run_owner_is_not_a_dispatch_owner_kind() -> None:
    assert ORCHESTRATION_RUN_INTAKE_OWNER_KIND == "orchestration_run"
    assert ORCHESTRATION_RUN_INTAKE_OWNER_KIND not in ORCHESTRATION_DISPATCH_OWNER_KINDS
    assert ORCHESTRATION_STEP_DISPATCH_OWNER_KIND in ORCHESTRATION_DISPATCH_OWNER_KINDS


def test_execution_chain_domain_tracks_step_and_terminal_state() -> None:
    chain = ExecutionChain.create(chain_id="chain-1", turn_id="run-1")

    chain.start(active_step_id="step-1")
    chain.increment_step_count()
    chain.wait(active_step_id="step-1")
    chain.complete()

    assert chain.status is ExecutionChainStatus.COMPLETED
    assert chain.step_count == 1
    assert chain.active_step_id is None
    assert chain.completed_at is not None


def test_fail_active_execution_step_fails_chain_when_active_step_is_terminal() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    run = OrchestrationRun.accept(
        run_id="run-max-step-terminal-active",
        inbound_instruction=InboundInstruction(source="unit", content="hello"),
        metadata={"session_key": "session-max-step-terminal-active"},
    )

    with uow:
        uow.orchestration_runs.add(run)
        chain = ExecutionChain.create(
            chain_id="chain-max-step-terminal-active",
            turn_id=run.id,
        )
        chain.start(active_step_id="step-max-step-terminal-active")
        chain.increment_step_count()
        step = ExecutionStep.create(
            step_id="step-max-step-terminal-active",
            chain_id=chain.id,
            turn_id=chain.turn_id,
            step_index=0,
            kind=ExecutionStepKind.TOOL_BATCH,
            correlation_key="run-max-step-terminal-active:0:tool",
        )
        step.complete()
        uow.execution_chains.add(chain)
        uow.execution_steps.add(step)
        uow.commit()

    with uow:
        observed = fail_active_execution_step(
            uow,
            run=run,
            message="Run exceeded max steps.",
            code="max_steps_exceeded",
            details={"max_steps": run.max_steps},
        )
        assert observed is not None
        uow.commit()

    query = OrchestrationRunQueryService(lambda: uow)
    [observed_chain] = query.list_execution_chains(run.id)
    observed_step = query.get_execution_step("step-max-step-terminal-active")
    assert observed_step.status is ExecutionStepStatus.COMPLETED
    assert observed_chain.status is ExecutionChainStatus.FAILED
    assert observed_chain.error_payload is not None
    assert observed_chain.error_payload.code == "max_steps_exceeded"


def test_cancel_active_execution_step_cancels_chain_when_active_step_is_terminal() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    run = OrchestrationRun.accept(
        run_id="run-cancel-terminal-active",
        inbound_instruction=InboundInstruction(source="unit", content="stop"),
        metadata={"session_key": "session-cancel-terminal-active"},
    )

    with uow:
        uow.orchestration_runs.add(run)
        chain = ExecutionChain.create(
            chain_id="chain-cancel-terminal-active",
            turn_id=run.id,
        )
        chain.start(active_step_id="step-cancel-terminal-active")
        chain.increment_step_count()
        step = ExecutionStep.create(
            step_id="step-cancel-terminal-active",
            chain_id=chain.id,
            turn_id=chain.turn_id,
            step_index=0,
            kind=ExecutionStepKind.LLM,
            correlation_key="run-cancel-terminal-active:0:llm",
        )
        step.complete()
        uow.execution_chains.add(chain)
        uow.execution_steps.add(step)
        uow.commit()

    with uow:
        observed = cancel_active_execution_step(uow, run=run)
        assert observed is not None
        uow.commit()

    query = OrchestrationRunQueryService(lambda: uow)
    [observed_chain] = query.list_execution_chains(run.id)
    observed_step = query.get_execution_step("step-cancel-terminal-active")
    assert observed_step.status is ExecutionStepStatus.COMPLETED
    assert observed_chain.status is ExecutionChainStatus.CANCELLED
    assert observed_chain.active_step_id is None


def test_execution_step_domain_tracks_state_transitions() -> None:
    step = ExecutionStep.create(
        step_id="step-transition",
        chain_id="chain-transition",
        turn_id="run-transition",
        step_index=0,
        kind=ExecutionStepKind.LLM,
    )

    assert step.status is ExecutionStepStatus.CREATED
    step.start()
    started_at = step.started_at
    assert step.status is ExecutionStepStatus.RUNNING
    assert started_at is not None

    step.wait()
    assert step.status is ExecutionStepStatus.WAITING
    assert step.started_at == started_at
    assert step.completed_at is None

    step.complete()
    assert step.status is ExecutionStepStatus.COMPLETED
    assert step.completed_at is not None
    assert step.error_payload is None

    failed_step = ExecutionStep.create(
        step_id="step-transition-failed",
        chain_id="chain-transition",
        turn_id="run-transition",
        step_index=1,
        kind=ExecutionStepKind.TOOL_BATCH,
    )
    failed_step.fail(
        message="tool failed",
        code="tool_failed",
        details={"tool_run_id": "tool-run-transition"},
    )
    assert failed_step.status is ExecutionStepStatus.FAILED
    assert failed_step.completed_at is not None
    assert failed_step.error_payload is not None
    assert failed_step.error_payload.code == "tool_failed"
    assert failed_step.error_payload.details == {
        "tool_run_id": "tool-run-transition",
    }

    cancelled_step = ExecutionStep.create(
        step_id="step-transition-cancelled",
        chain_id="chain-transition",
        turn_id="run-transition",
        step_index=2,
        kind=ExecutionStepKind.APPROVAL,
    )
    cancelled_step.cancel()
    assert cancelled_step.status is ExecutionStepStatus.CANCELLED
    assert cancelled_step.completed_at is not None


def test_execution_step_item_owner_reference_validates_empty_values() -> None:
    try:
        ExecutionOwnerReference(owner_kind="tool_run", owner_id=" ")
    except OrchestrationValidationError:
        pass
    else:
        raise AssertionError("empty owner_id should fail validation")

    assert ExecutionOwnerReference.of(
        ExecutionOwnerKind.TOOL_RUN,
        "tool-run-1",
    ).to_payload() == {
        "owner_kind": "tool_run",
        "owner_id": "tool-run-1",
    }
    assert ExecutionOwnerReference.llm_invocation("llm-1") == ExecutionOwnerReference(
        owner_kind="llm_invocation",
        owner_id="llm-1",
    )
    assert ExecutionOwnerReference.session_item("item-1").owner_kind == "session_item"


def test_execution_chain_repositories_round_trip_entities() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        chain_repo = SqlAlchemyExecutionChainRepository(session)
        step_repo = SqlAlchemyExecutionStepRepository(session)
        item_repo = SqlAlchemyExecutionStepItemRepository(session)

        chain = ExecutionChain.create(chain_id="chain-1", turn_id="run-1")
        chain.start(active_step_id="step-1")
        chain.increment_step_count()
        step = ExecutionStep.create(
            step_id="step-1",
            chain_id=chain.id,
            turn_id=chain.turn_id,
            step_index=0,
            kind=ExecutionStepKind.LLM,
            correlation_key="run-1:chain-1:0:llm",
        )
        step.start()
        step.link_owner(
            ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id="invocation-1",
            ),
        )
        item = ExecutionStepItem.create(
            item_id="item-1",
            step_id=step.id,
            chain_id=chain.id,
            turn_id=chain.turn_id,
            item_index=0,
            kind=ExecutionStepItemKind.LLM_INVOCATION,
            owner=ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id="invocation-1",
            ),
        )
        item.complete(summary_payload={"finish_reason": "stop"})

        chain_repo.add(chain)
        step_repo.add(step)
        item_repo.add(item)
        session.commit()

    with session_factory() as session:
        chain_repo = SqlAlchemyExecutionChainRepository(session)
        step_repo = SqlAlchemyExecutionStepRepository(session)
        item_repo = SqlAlchemyExecutionStepItemRepository(session)

        loaded_chain = chain_repo.get("chain-1")
        assert loaded_chain is not None
        assert loaded_chain.status is ExecutionChainStatus.RUNNING
        assert loaded_chain.active_step_id == "step-1"

        loaded_step = step_repo.get_by_correlation_key("run-1:chain-1:0:llm")
        assert loaded_step is not None
        assert loaded_step.status is ExecutionStepStatus.RUNNING
        assert loaded_step.owner == ExecutionOwnerReference(
            owner_kind="llm_invocation",
            owner_id="invocation-1",
        )

        owner_matches = item_repo.find_by_owner_reference(
            ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id="invocation-1",
            ),
            status=ExecutionStepItemStatus.COMPLETED,
        )
        assert [item.id for item in owner_matches] == ["item-1"]
        assert owner_matches[0].summary_payload == {"finish_reason": "stop"}


def test_sqlalchemy_uow_exposes_execution_chain_repositories() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    uow = SqlAlchemyUnitOfWork(session_factory)
    with uow:
        uow.execution_chains.add(
            ExecutionChain.create(chain_id="chain-uow", turn_id="run-uow"),
        )
        uow.execution_steps.add(
            ExecutionStep.create(
                step_id="step-uow",
                chain_id="chain-uow",
                turn_id="run-uow",
                step_index=0,
                kind=ExecutionStepKind.PROMPT_RENDER,
            ),
        )
        uow.execution_step_items.add(
            ExecutionStepItem.create(
                item_id="item-uow",
                step_id="step-uow",
                chain_id="chain-uow",
                turn_id="run-uow",
                item_index=0,
                kind=ExecutionStepItemKind.CONTEXT_SNAPSHOT,
                owner=ExecutionOwnerReference(
                    owner_kind="context_snapshot",
                    owner_id="snapshot-1",
                ),
            ),
        )
        uow.commit()

    with uow:
        assert uow.execution_chains.get("chain-uow") is not None
        assert uow.execution_steps.get("step-uow") is not None
        assert uow.execution_step_items.get("item-uow") is not None


def test_run_query_service_exposes_execution_chain_read_surface() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    uow = SqlAlchemyUnitOfWork(session_factory)
    with uow:
        chain = ExecutionChain.create(chain_id="chain-query", turn_id="run-query")
        chain.start(active_step_id="step-query")
        chain.increment_step_count()
        uow.execution_chains.add(chain)
        step = ExecutionStep.create(
            step_id="step-query",
            chain_id=chain.id,
            turn_id=chain.turn_id,
            step_index=0,
            kind=ExecutionStepKind.TOOL_BATCH,
            correlation_key="run-query:tool-batch:0",
        )
        step.wait()
        uow.execution_steps.add(step)
        item = ExecutionStepItem.create(
            item_id="item-query",
            step_id=step.id,
            chain_id=chain.id,
            turn_id=chain.turn_id,
            item_index=0,
            kind=ExecutionStepItemKind.TOOL_RUN,
            owner=ExecutionOwnerReference(
                owner_kind="tool_run",
                owner_id="tool-run-query",
            ),
        )
        item.wait()
        uow.execution_step_items.add(item)
        uow.commit()

    query = OrchestrationRunQueryService(lambda: uow)
    owner = ExecutionOwnerReference(
        owner_kind="tool_run",
        owner_id="tool-run-query",
    )

    assert query.get_active_execution_chain("run-query").id == "chain-query"
    assert [chain.id for chain in query.list_execution_chains("run-query")] == [
        "chain-query",
    ]
    assert query.get_execution_step("step-query").status is ExecutionStepStatus.WAITING
    assert (
        query.get_execution_step_by_correlation_key("run-query:tool-batch:0").id
        == "step-query"
    )
    assert [step.id for step in query.list_execution_steps("chain-query")] == [
        "step-query",
    ]
    assert query.get_execution_step_item("item-query").kind is ExecutionStepItemKind.TOOL_RUN
    assert [item.id for item in query.list_execution_step_items("step-query")] == [
        "item-query",
    ]
    snapshots = query.list_execution_chain_snapshots("run-query")
    assert [snapshot.chain.id for snapshot in snapshots] == ["chain-query"]
    assert [step_snapshot.step.id for step_snapshot in snapshots[0].steps] == [
        "step-query",
    ]
    assert [item.id for item in snapshots[0].steps[0].items] == ["item-query"]
    assert [
        item.id
        for item in query.find_execution_step_items_by_owner(
            owner,
            status=ExecutionStepItemStatus.WAITING,
        )
    ] == ["item-query"]


def test_intake_accept_and_enqueue_materializes_execution_chain_steps() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    intake = RunIntakeCoordinator(
        uow_factory=lambda: uow,
        scheduler=OrchestrationScheduler(),
        dispatch_port=OrchestrationDispatchAdapter(),
        plan_prepared_session_run=lambda _data: None,
    )

    run = intake.accept(
        AcceptOrchestrationRunInput(
            run_id="run-exec-chain-intake",
            inbound_instruction=InboundInstruction(source="unit", content="hello"),
        ),
    )
    query = OrchestrationRunQueryService(lambda: uow)
    chain = query.get_active_execution_chain(run.id)
    assert chain is not None
    assert chain.status is ExecutionChainStatus.WAITING
    [intake_step] = query.list_execution_steps(chain.id)
    assert intake_step.kind is ExecutionStepKind.INTAKE
    assert intake_step.status is ExecutionStepStatus.WAITING
    assert intake_step.owner == ExecutionOwnerReference(
        owner_kind="orchestration_run",
        owner_id=run.id,
    )

    intake.enqueue(
        EnqueueOrchestrationRunInput(
            run_id=run.id,
            queue_policy=OrchestrationQueuePolicy.FIFO,
            priority=10,
        ),
    )

    chain = query.get_active_execution_chain(run.id)
    assert chain is not None
    steps = query.list_execution_steps(chain.id)
    assert [(step.step_index, step.kind, step.status) for step in steps] == [
        (0, ExecutionStepKind.INTAKE, ExecutionStepStatus.COMPLETED),
        (1, ExecutionStepKind.LLM, ExecutionStepStatus.CREATED),
    ]
    assert chain.active_step_id == steps[1].id
    assert steps[1].dispatch_task_id == steps[1].id
    assert steps[1].owner == ExecutionOwnerReference(
        owner_kind=ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
        owner_id=steps[1].id,
    )


def test_ingress_submit_materializes_intake_execution_step_for_request() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    ingress = RunIngressCoordinator(uow_factory=lambda: uow)

    run = ingress.submit_turn(
        SubmitOrchestrationTurnInput(
            accept_input=AcceptOrchestrationRunInput(
                run_id="run-exec-chain-ingress",
                inbound_instruction=InboundInstruction(source="webhook", content="hi"),
                queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            ),
            context=SessionRouteContext(
                agent_id="assistant",
                channel="webchat",
                direct_scope=DirectSessionScope.MAIN,
            ),
        ),
    )
    query = OrchestrationRunQueryService(lambda: uow)
    chain = query.get_active_execution_chain(run.id)
    assert chain is not None
    [intake_step] = query.list_execution_steps(chain.id)

    with uow:
        request = uow.orchestration_ingress_requests.get_by_run_id(run.id)

    assert request is not None
    assert intake_step.kind is ExecutionStepKind.INTAKE
    assert intake_step.status is ExecutionStepStatus.WAITING
    assert intake_step.owner == ExecutionOwnerReference(
        owner_kind="orchestration_ingress_request",
        owner_id=request.id,
    )


def test_progress_coordinator_records_llm_step_and_invocation_item() -> None:
    engine = _create_sqlite_engine_with_foreign_keys()
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    intake = RunIntakeCoordinator(
        uow_factory=lambda: uow,
        scheduler=OrchestrationScheduler(),
        dispatch_port=OrchestrationDispatchAdapter(),
        plan_prepared_session_run=lambda _data: None,
    )
    progress = RunProgressCoordinator(
        uow_factory=lambda: uow,
        dispatch_port=OrchestrationDispatchAdapter(),
        lease_manager=None,
        advance_once=lambda _run_id, _worker_id: None,
        heartbeat_assignment=lambda _run_id, _worker_id: None,
        get_run=lambda run_id: OrchestrationRunQueryService(lambda: uow).get_run(run_id),
        apply_compaction_summary=lambda _run: None,
        maybe_request_auto_compaction=lambda _run: None,
        clear_pending_compaction_marker=lambda _run: None,
        clear_pending_memory_flush_marker=lambda _run: None,
        is_compaction_run=lambda _run: False,
        is_memory_flush_run=lambda _run: False,
    )
    run = intake.accept(
        AcceptOrchestrationRunInput(
            run_id="run-exec-chain-progress",
            inbound_instruction=InboundInstruction(source="unit", content="hello"),
        ),
    )
    intake.enqueue(EnqueueOrchestrationRunInput(run_id=run.id))

    with uow:
        claimed = uow.orchestration_runs.get(run.id)
        assert claimed is not None
        claimed.claim(worker_id="worker-1", acquire_lane_lock=False)
        uow.orchestration_runs.add(claimed)
        uow.collect(claimed)
        uow.commit()

    progress.advance_assignment(
        AdvanceAssignmentInput(
            run_id=run.id,
            worker_id="worker-1",
            stage=OrchestrationRunStage.LLM,
            step_increment=1,
        ),
    )
    progress.complete_assignment(
        CompleteAssignmentInput(
            run_id=run.id,
            worker_id="worker-1",
            result_payload={
                "llm_id": "llm-primary",
            },
            execution_payload={
                "llm_invocation_id": "invocation-progress-1",
                "assistant_progress_item_ids": ["item-assistant-1"],
            },
        ),
    )

    query = OrchestrationRunQueryService(lambda: uow)
    assert query.get_active_execution_chain(run.id) is None
    [completed_chain] = query.list_execution_chains(
        run.id,
        status=ExecutionChainStatus.COMPLETED,
    )
    steps = query.list_execution_steps(completed_chain.id)
    assert [(step.step_index, step.kind, step.status) for step in steps] == [
        (0, ExecutionStepKind.INTAKE, ExecutionStepStatus.COMPLETED),
        (1, ExecutionStepKind.LLM, ExecutionStepStatus.COMPLETED),
        (2, ExecutionStepKind.FINAL_RESPONSE, ExecutionStepStatus.COMPLETED),
    ]
    items = query.find_execution_step_items_by_owner(
        ExecutionOwnerReference(
            owner_kind="llm_invocation",
            owner_id="invocation-progress-1",
        ),
    )
    assert [item.kind for item in items] == [ExecutionStepItemKind.LLM_INVOCATION]
    assert items[0].summary_payload == {
        "llm_invocation_id": "invocation-progress-1",
        "assistant_progress_item_ids": ["item-assistant-1"],
        "llm_id": "llm-primary",
    }
    session_item_items = query.find_execution_step_items_by_owner(
        ExecutionOwnerReference(
            owner_kind="session_item",
            owner_id="item-assistant-1",
        ),
    )
    assert [item.kind for item in session_item_items] == [
        ExecutionStepItemKind.SESSION_MESSAGE,
    ]
    assert session_item_items[0].summary_payload == {
        "session_item_id": "item-assistant-1",
        "message_role": "assistant",
        "llm_invocation_id": "invocation-progress-1",
        "message_kind": "assistant_progress",
        "assistant_progress_item_ids": ["item-assistant-1"],
        "llm_id": "llm-primary",
    }


def test_progress_coordinator_records_llm_continuation_decision_item() -> None:
    engine = _create_sqlite_engine_with_foreign_keys()
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    intake = RunIntakeCoordinator(
        uow_factory=lambda: uow,
        scheduler=OrchestrationScheduler(),
        dispatch_port=OrchestrationDispatchAdapter(),
        plan_prepared_session_run=lambda _data: None,
    )
    progress = RunProgressCoordinator(
        uow_factory=lambda: uow,
        dispatch_port=OrchestrationDispatchAdapter(),
        lease_manager=None,
        advance_once=lambda _run_id, _worker_id: None,
        heartbeat_assignment=lambda _run_id, _worker_id: None,
        get_run=lambda run_id: OrchestrationRunQueryService(lambda: uow).get_run(run_id),
        apply_compaction_summary=lambda _run: None,
        maybe_request_auto_compaction=lambda _run: None,
        clear_pending_compaction_marker=lambda _run: None,
        clear_pending_memory_flush_marker=lambda _run: None,
        is_compaction_run=lambda _run: False,
        is_memory_flush_run=lambda _run: False,
    )
    run = intake.accept(
        AcceptOrchestrationRunInput(
            run_id="run-exec-chain-continuation",
            inbound_instruction=InboundInstruction(source="unit", content="hello"),
        ),
    )
    intake.enqueue(EnqueueOrchestrationRunInput(run_id=run.id))

    with uow:
        claimed = uow.orchestration_runs.get(run.id)
        assert claimed is not None
        claimed.claim(worker_id="worker-1", acquire_lane_lock=False)
        uow.orchestration_runs.add(claimed)
        uow.collect(claimed)
        uow.commit()

    progress.advance_assignment(
        AdvanceAssignmentInput(
            run_id=run.id,
            worker_id="worker-1",
            stage=OrchestrationRunStage.LLM,
            step_increment=1,
        ),
    )
    progress.complete_assignment(
        CompleteAssignmentInput(
            run_id=run.id,
            worker_id="worker-1",
            result_payload={
                "llm_id": "llm-primary",
                "continuation_reason": "provider_end_turn_false",
                "continuation_end_turn": False,
            },
            execution_payload={
                "llm_invocation_id": "invocation-continuation-1",
                "llm_continuation_reason": "provider_end_turn_false",
                "llm_continuation_end_turn": False,
                "llm_continuation_follow_up": True,
            },
        ),
    )

    query = OrchestrationRunQueryService(lambda: uow)
    items = query.find_execution_step_items_by_owner(
        ExecutionOwnerReference(
            owner_kind="llm_continuation",
            owner_id="invocation-continuation-1:continuation",
        ),
    )
    assert [item.kind for item in items] == [
        ExecutionStepItemKind.CONTINUATION_DECISION,
    ]
    assert items[0].summary_payload == {
        "llm_invocation_id": "invocation-continuation-1",
        "continuation_id": "invocation-continuation-1:continuation",
        "reason": "provider_end_turn_false",
        "end_turn": False,
        "needs_follow_up": True,
    }


def test_execution_payload_keeps_tool_call_items_out_of_assistant_progress() -> None:
    payload = RunExecutionService._execution_payload_from_outcome(
        EngineAdvanceOutcome(
            llm_id="llm-primary",
            llm_invocation_id="invocation-tool-text",
            response_text="我先检查页面状态。",
            assistant_progress_item_ids=("item-progress-1",),
            tool_call_session_item_ids=(
                "item-function-call-1",
                "item-function-call-2",
            ),
            tool_call_names=("browser.snapshot", "browser.click"),
        ),
    )

    assert payload["assistant_progress_item_ids"] == ["item-progress-1"]
    assert payload["tool_call_session_item_ids"] == [
        "item-function-call-1",
        "item-function-call-2",
    ]
    assert payload["assistant_progress_text"] == "我先检查页面状态。"


def test_progress_coordinator_materializes_tool_batch_step_items() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    intake = RunIntakeCoordinator(
        uow_factory=lambda: uow,
        scheduler=OrchestrationScheduler(),
        dispatch_port=OrchestrationDispatchAdapter(),
        plan_prepared_session_run=lambda _data: None,
    )
    progress = RunProgressCoordinator(
        uow_factory=lambda: uow,
        dispatch_port=OrchestrationDispatchAdapter(),
        lease_manager=None,
        advance_once=lambda _run_id, _worker_id: None,
        heartbeat_assignment=lambda _run_id, _worker_id: None,
        get_run=lambda run_id: OrchestrationRunQueryService(lambda: uow).get_run(run_id),
        apply_compaction_summary=lambda _run: None,
        maybe_request_auto_compaction=lambda _run: None,
        clear_pending_compaction_marker=lambda _run: None,
        clear_pending_memory_flush_marker=lambda _run: None,
        is_compaction_run=lambda _run: False,
        is_memory_flush_run=lambda _run: False,
    )
    run = intake.accept(
        AcceptOrchestrationRunInput(
            run_id="run-exec-chain-tool-batch",
            inbound_instruction=InboundInstruction(source="unit", content="hello"),
        ),
    )
    intake.enqueue(EnqueueOrchestrationRunInput(run_id=run.id))

    with uow:
        claimed = uow.orchestration_runs.get(run.id)
        assert claimed is not None
        claimed.claim(worker_id="worker-1", acquire_lane_lock=False)
        uow.orchestration_runs.add(claimed)
        uow.collect(claimed)
        uow.commit()

    progress.advance_assignment(
        AdvanceAssignmentInput(
            run_id=run.id,
            worker_id="worker-1",
            stage=OrchestrationRunStage.LLM,
            step_increment=1,
        ),
    )
    progress.advance_assignment(
        AdvanceAssignmentInput(
            run_id=run.id,
            worker_id="worker-1",
            stage=OrchestrationRunStage.TOOL,
            metadata={
                "llm_id": "llm-primary",
            },
            execution_payload={
                "llm_id": "llm-primary",
                "llm_invocation_id": "invocation-tool-batch-1",
                "context_render_snapshot_id": "ctxsnap-tool-batch-1",
                "llm_response_item_ids": [
                    "invocation-tool-batch-1:item:assistant",
                    "invocation-tool-batch-1:item:tool-call",
                ],
                "assistant_progress_item_ids": ["item-progress-1"],
                "assistant_progress_text": "我看到 echo 和 image 工具可用，先验证工具调用链。",
                "tool_call_names": ["echo", "image_generate"],
                "tool_run_links": [
                    {
                        "tool_call_id": "call-inline-1",
                        "tool_name": "echo",
                        "tool_run_id": "tool-run-inline-1",
                        "tool_id": "echo",
                        "status": "completed",
                        "mode": "sync",
                        "strategy": "inline",
                        "environment": "local",
                        "result_session_item_id": "session-item-tool-result-1",
                        "background": False,
                        "tool_execution_plan": {
                            "tool_call_id": "call-inline-1",
                            "tool_name": "echo",
                            "tool_id": "echo",
                            "mode": "sync",
                            "strategy": "inline",
                            "environment": "local",
                            "resource_policy": {
                                "timeout_seconds": 30,
                            },
                            "arguments_digest": "digest-inline-1",
                        },
                        "tool_lifecycle": {
                            "superseded": True,
                            "superseded_by_tool_call_id": "call-inline-2",
                            "supersedes_tool_call_id": "call-inline-0",
                        },
                    },
                    {
                        "tool_call_id": "call-background-1",
                        "tool_name": "openai_image_generate",
                        "tool_run_id": "tool-run-background-1",
                        "tool_id": "openai_image_generate",
                        "status": "queued",
                        "mode": "async",
                        "strategy": "background",
                        "environment": "remote",
                        "background": True,
                    },
                ],
            },
        ),
    )

    query = OrchestrationRunQueryService(lambda: uow)
    chain = query.get_active_execution_chain(run.id)
    assert chain is not None
    assert chain.status is ExecutionChainStatus.WAITING
    steps = query.list_execution_steps(chain.id)
    assert [(step.step_index, step.kind, step.status) for step in steps] == [
        (0, ExecutionStepKind.INTAKE, ExecutionStepStatus.COMPLETED),
        (1, ExecutionStepKind.LLM, ExecutionStepStatus.COMPLETED),
        (2, ExecutionStepKind.TOOL_BATCH, ExecutionStepStatus.WAITING),
    ]
    tool_step = steps[2]
    assert chain.active_step_id == tool_step.id
    llm_step = steps[1]

    llm_items = query.find_execution_step_items_by_owner(
        ExecutionOwnerReference(
            owner_kind="llm_invocation",
            owner_id="invocation-tool-batch-1",
        ),
    )
    assert [item.kind for item in llm_items] == [
        ExecutionStepItemKind.LLM_INVOCATION,
    ]
    progress_items = query.list_execution_step_items(llm_step.id)
    assert [
        (item.kind, item.owner, item.status, item.correlation_key)
        for item in progress_items
    ] == [
        (
            ExecutionStepItemKind.LLM_INVOCATION,
            ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id="invocation-tool-batch-1",
            ),
            ExecutionStepItemStatus.COMPLETED,
            "invocation-tool-batch-1",
        ),
        (
            ExecutionStepItemKind.SESSION_MESSAGE,
            ExecutionOwnerReference(
                owner_kind="session_item",
                owner_id="item-progress-1",
            ),
            ExecutionStepItemStatus.COMPLETED,
            "item-progress-1",
        ),
    ]
    assert progress_items[0].summary_payload == {
        "llm_invocation_id": "invocation-tool-batch-1",
        "assistant_progress_item_ids": ["item-progress-1"],
        "context_render_snapshot_id": "ctxsnap-tool-batch-1",
        "llm_id": "llm-primary",
        "llm_response_item_ids": [
            "invocation-tool-batch-1:item:assistant",
            "invocation-tool-batch-1:item:tool-call",
        ],
        "tool_call_names": ["echo", "image_generate"],
        "assistant_progress_text": "我看到 echo 和 image 工具可用，先验证工具调用链。",
        "assistant_progress_text_chars": 31,
    }
    assert progress_items[1].summary_payload == {
        "session_item_id": "item-progress-1",
        "message_role": "assistant",
        "llm_invocation_id": "invocation-tool-batch-1",
        "message_kind": "assistant_progress",
        "assistant_progress_item_ids": ["item-progress-1"],
        "context_render_snapshot_id": "ctxsnap-tool-batch-1",
        "assistant_progress_text": "我看到 echo 和 image 工具可用，先验证工具调用链。",
        "assistant_progress_text_chars": 31,
        "llm_id": "llm-primary",
        "llm_response_item_ids": [
            "invocation-tool-batch-1:item:assistant",
            "invocation-tool-batch-1:item:tool-call",
        ],
        "tool_call_names": ["echo", "image_generate"],
    }

    tool_items = query.list_execution_step_items(tool_step.id)
    assert [
        (item.kind, item.owner, item.status, item.correlation_key)
        for item in tool_items
    ] == [
        (
            ExecutionStepItemKind.TOOL_CALL,
            ExecutionOwnerReference(owner_kind="tool_call", owner_id="call-inline-1"),
            ExecutionStepItemStatus.COMPLETED,
            "call-inline-1",
        ),
        (
            ExecutionStepItemKind.TOOL_RUN,
            ExecutionOwnerReference(
                owner_kind="tool_run",
                owner_id="tool-run-inline-1",
            ),
            ExecutionStepItemStatus.COMPLETED,
            "call-inline-1",
        ),
        (
            ExecutionStepItemKind.TOOL_RESULT,
            ExecutionOwnerReference(
                owner_kind="session_item",
                owner_id="session-item-tool-result-1",
            ),
            ExecutionStepItemStatus.COMPLETED,
            "call-inline-1",
        ),
        (
            ExecutionStepItemKind.TOOL_CALL,
            ExecutionOwnerReference(
                owner_kind="tool_call",
                owner_id="call-background-1",
            ),
            ExecutionStepItemStatus.COMPLETED,
            "call-background-1",
        ),
        (
            ExecutionStepItemKind.TOOL_RUN,
            ExecutionOwnerReference(
                owner_kind="tool_run",
                owner_id="tool-run-background-1",
            ),
            ExecutionStepItemStatus.WAITING,
            "call-background-1",
        ),
    ]
    assert tool_items[1].summary_payload == {
        "tool_run_id": "tool-run-inline-1",
        "tool_call_id": "call-inline-1",
        "tool_name": "echo",
        "tool_id": "echo",
        "status": "completed",
        "result_session_item_id": "session-item-tool-result-1",
        "background": False,
        "mode": "sync",
        "strategy": "inline",
        "environment": "local",
        "tool_execution_plan": {
            "tool_call_id": "call-inline-1",
            "tool_name": "echo",
            "tool_id": "echo",
            "mode": "sync",
            "strategy": "inline",
            "environment": "local",
            "resource_policy": {
                "timeout_seconds": 30,
            },
            "arguments_digest": "digest-inline-1",
        },
        "tool_lifecycle": {
            "superseded": True,
            "superseded_by_tool_call_id": "call-inline-2",
            "supersedes_tool_call_id": "call-inline-0",
        },
    }
    assert tool_items[2].summary_payload == {
        "tool_run_id": "tool-run-inline-1",
        "tool_call_id": "call-inline-1",
        "tool_name": "echo",
        "tool_id": "echo",
        "result_session_item_id": "session-item-tool-result-1",
        "tool_execution_plan": {
            "tool_call_id": "call-inline-1",
            "tool_name": "echo",
            "tool_id": "echo",
            "mode": "sync",
            "strategy": "inline",
            "environment": "local",
            "resource_policy": {
                "timeout_seconds": 30,
            },
            "arguments_digest": "digest-inline-1",
        },
        "tool_lifecycle": {
            "superseded": True,
            "superseded_by_tool_call_id": "call-inline-2",
            "supersedes_tool_call_id": "call-inline-0",
        },
    }
    assert tool_items[4].summary_payload == {
        "tool_run_id": "tool-run-background-1",
        "tool_call_id": "call-background-1",
        "tool_name": "openai_image_generate",
        "tool_id": "openai_image_generate",
        "status": "queued",
        "background": True,
        "mode": "async",
        "strategy": "background",
        "environment": "remote",
    }


def test_progress_coordinator_keeps_repeated_llm_tool_loops_in_distinct_steps() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    intake = RunIntakeCoordinator(
        uow_factory=lambda: uow,
        scheduler=OrchestrationScheduler(),
        dispatch_port=OrchestrationDispatchAdapter(),
        plan_prepared_session_run=lambda _data: None,
    )
    progress = RunProgressCoordinator(
        uow_factory=lambda: uow,
        dispatch_port=OrchestrationDispatchAdapter(),
        lease_manager=None,
        advance_once=lambda _run_id, _worker_id: None,
        heartbeat_assignment=lambda _run_id, _worker_id: None,
        get_run=lambda run_id: OrchestrationRunQueryService(lambda: uow).get_run(run_id),
        apply_compaction_summary=lambda _run: None,
        maybe_request_auto_compaction=lambda _run: None,
        clear_pending_compaction_marker=lambda _run: None,
        clear_pending_memory_flush_marker=lambda _run: None,
        is_compaction_run=lambda _run: False,
        is_memory_flush_run=lambda _run: False,
    )
    run = intake.accept(
        AcceptOrchestrationRunInput(
            run_id="run-exec-chain-repeated-loop",
            inbound_instruction=InboundInstruction(source="unit", content="hello"),
        ),
    )
    intake.enqueue(EnqueueOrchestrationRunInput(run_id=run.id))

    with uow:
        claimed = uow.orchestration_runs.get(run.id)
        assert claimed is not None
        claimed.claim(worker_id="worker-1", acquire_lane_lock=False)
        uow.orchestration_runs.add(claimed)
        uow.collect(claimed)
        uow.commit()

    def advance_to_llm() -> None:
        progress.advance_assignment(
            AdvanceAssignmentInput(
                run_id=run.id,
                worker_id="worker-1",
                stage=OrchestrationRunStage.LLM,
                step_increment=1,
            ),
        )

    def complete_tool_loop(loop_index: int) -> None:
        progress.advance_assignment(
            AdvanceAssignmentInput(
                run_id=run.id,
                worker_id="worker-1",
                stage=OrchestrationRunStage.TOOL,
                execution_payload={
                    "llm_invocation_id": f"invocation-loop-{loop_index}",
                    "tool_call_names": [f"tool-{loop_index}"],
                    "tool_run_links": [
                        {
                            "tool_call_id": f"call-loop-{loop_index}",
                            "tool_name": f"tool-{loop_index}",
                            "tool_run_id": f"tool-run-loop-{loop_index}",
                            "tool_id": f"tool-{loop_index}",
                            "status": "completed",
                            "result_session_item_id": f"session-item-tool-result-{loop_index}",
                            "background": False,
                        },
                    ],
                },
            ),
        )

    advance_to_llm()
    complete_tool_loop(1)
    advance_to_llm()
    complete_tool_loop(2)
    advance_to_llm()
    progress.complete_assignment(
        CompleteAssignmentInput(
            run_id=run.id,
            worker_id="worker-1",
            result_payload={
                "llm_id": "llm-primary",
                "session_item_ids": ["session-item-assistant-final"],
                "assistant_progress_item_ids": ["session-item-assistant-final"],
            },
            execution_payload={
                "llm_invocation_id": "invocation-loop-3",
            },
        ),
    )

    query = OrchestrationRunQueryService(lambda: uow)
    [chain] = query.list_execution_chains(
        run.id,
        status=ExecutionChainStatus.COMPLETED,
    )
    steps = query.list_execution_steps(chain.id)
    assert [(step.step_index, step.kind, step.status) for step in steps] == [
        (0, ExecutionStepKind.INTAKE, ExecutionStepStatus.COMPLETED),
        (1, ExecutionStepKind.LLM, ExecutionStepStatus.COMPLETED),
        (2, ExecutionStepKind.TOOL_BATCH, ExecutionStepStatus.COMPLETED),
        (3, ExecutionStepKind.LLM, ExecutionStepStatus.COMPLETED),
        (4, ExecutionStepKind.TOOL_BATCH, ExecutionStepStatus.COMPLETED),
        (5, ExecutionStepKind.LLM, ExecutionStepStatus.COMPLETED),
        (6, ExecutionStepKind.FINAL_RESPONSE, ExecutionStepStatus.COMPLETED),
    ]
    invocation_step_indices = {}
    for step in steps:
        for item in query.list_execution_step_items(step.id):
            if item.kind is ExecutionStepItemKind.LLM_INVOCATION:
                invocation_step_indices[item.owner.owner_id] = step.step_index
    assert invocation_step_indices == {
        "invocation-loop-1": 1,
        "invocation-loop-2": 3,
        "invocation-loop-3": 5,
    }


def test_tool_run_terminal_observation_closes_waiting_step_item() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)

    with uow:
        chain = ExecutionChain.create(
            chain_id="chain-terminal-tool",
            turn_id="run-terminal-tool",
        )
        chain.increment_step_count()
        chain.wait(active_step_id="step-terminal-tool")
        step = ExecutionStep.create(
            step_id="step-terminal-tool",
            chain_id=chain.id,
            turn_id=chain.turn_id,
            step_index=0,
            kind=ExecutionStepKind.TOOL_BATCH,
            correlation_key="run-terminal-tool:tool-batch:invocation-1",
        )
        step.wait()
        tool_call = ExecutionStepItem.create(
            item_id="item-terminal-tool-call",
            step_id=step.id,
            chain_id=chain.id,
            turn_id=chain.turn_id,
            item_index=0,
            kind=ExecutionStepItemKind.TOOL_CALL,
            owner=ExecutionOwnerReference(
                owner_kind="tool_call",
                owner_id="call-terminal-tool",
            ),
        )
        tool_call.complete(summary_payload={"tool_name": "background_echo"})
        tool_run = ExecutionStepItem.create(
            item_id="item-terminal-tool-run",
            step_id=step.id,
            chain_id=chain.id,
            turn_id=chain.turn_id,
            item_index=1,
            kind=ExecutionStepItemKind.TOOL_RUN,
            owner=ExecutionOwnerReference(
                owner_kind="tool_run",
                owner_id="tool-run-terminal",
            ),
            correlation_key="call-terminal-tool",
        )
        tool_run.wait()
        uow.execution_chains.add(chain)
        uow.execution_steps.add(step)
        uow.execution_step_items.add(tool_call)
        uow.execution_step_items.add(tool_run)
        uow.commit()

    with uow:
        observed = mark_tool_run_step_item_terminal(
            uow,
            tool_run_id="tool-run-terminal",
            status="succeeded",
            summary_payload={
                "tool_id": "background_echo",
                "mode": "background",
            },
        )
        assert observed is not None
        uow.commit()

    query = OrchestrationRunQueryService(lambda: uow)
    item = query.get_execution_step_item("item-terminal-tool-run")
    assert item.status is ExecutionStepItemStatus.COMPLETED
    assert item.summary_payload == {
        "tool_run_id": "tool-run-terminal",
        "status": "succeeded",
        "tool_id": "background_echo",
        "mode": "background",
    }
    step = query.get_execution_step("step-terminal-tool")
    assert step.status is ExecutionStepStatus.COMPLETED
    [chain] = query.list_execution_chains("run-terminal-tool")
    assert chain.status is ExecutionChainStatus.WAITING
    assert chain.active_step_id == "step-terminal-tool"


def test_background_tool_result_message_uses_execution_item_reference() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    run = OrchestrationRun.accept(
        run_id="run-background-result-reference",
        inbound_instruction=InboundInstruction(source="unit", content="hello"),
        metadata={"session_key": "session-key"},
    )
    run.active_session_id = "session-instance"

    with uow:
        chain = ExecutionChain.create(
            chain_id="chain-background-result-reference",
            turn_id=run.id,
        )
        chain.start(active_step_id="step-background-llm")
        chain.increment_step_count()
        step = ExecutionStep.create(
            step_id="step-background-llm",
            chain_id=chain.id,
            turn_id=chain.turn_id,
            step_index=0,
            kind=ExecutionStepKind.LLM,
            correlation_key="run-background-result-reference:0:llm",
        )
        step.complete()
        uow.execution_chains.add(chain)
        uow.execution_steps.add(step)
        materialize_tool_batch_execution_step(
            uow,
            run=run,
            llm_invocation_id="llm-background-1",
            tool_run_links=(
                {
                    "tool_call_id": "call-background-result",
                    "tool_name": "openai_image_generate",
                    "tool_run_id": "tool-run-background-result",
                    "tool_id": "openai_image_generate",
                    "status": "queued",
                    "background": True,
                },
            ),
        )
        mark_tool_run_step_item_terminal(
            uow,
            tool_run_id="tool-run-background-result",
            status="succeeded",
            summary_payload={"tool_id": "openai_image_generate"},
        )
        uow.commit()

    query = OrchestrationRunQueryService(lambda: uow)
    [item] = query.find_execution_step_items_by_owner(
        ExecutionOwnerReference(
            owner_kind="tool_run",
            owner_id="tool-run-background-result",
        ),
    )
    assert item.summary_payload["tool_call_id"] == "call-background-result"
    assert item.summary_payload["tool_name"] == "openai_image_generate"

    tool_run = ToolRun.create(
        run_id="tool-run-background-result",
        tool_id="openai_image_generate",
        input_payload={},
        target=ToolExecutionTarget(mode=ToolMode.BACKGROUND),
    )
    tool_run.succeed(ToolRunResult(content=[text_content_block("image ready")]))
    session_service = _FakeSessionRecorderPort()
    recorder = OrchestrationSessionRecorder(
        session_service=session_service,
        execution_item_lookup=query,
    )

    item_ids = recorder.append_completed_background_tool_results(
        run,
        tool_runs=(tool_run,),
    )

    assert item_ids == ("item-1",)
    [session_item] = session_service.items
    assert session_item.kind.value == "tool_result"
    assert session_item.source_module == "tool"
    assert session_item.source_kind == "tool_run"
    assert session_item.source_id == "tool-run-background-result"
    assert session_item.call_id == "call-background-result"
    assert session_item.tool_name == "openai_image_generate"
    assert session_item.content_payload["tool_call_id"] == "call-background-result"

    with uow:
        materialized_items = materialize_tool_result_session_item_items(
            uow,
            run=run,
            tool_result_item_links=((tool_run.id, item_ids[0]),),
        )
        uow.commit()

    assert [item.kind for item in materialized_items] == [
        ExecutionStepItemKind.TOOL_RESULT,
    ]
    result_session_item_items = query.find_execution_step_items_by_owner(
        ExecutionOwnerReference(
            owner_kind="session_item",
            owner_id=item_ids[0],
        ),
    )
    assert [item.kind for item in result_session_item_items] == [
        ExecutionStepItemKind.TOOL_RESULT,
    ]
    assert result_session_item_items[0].summary_payload == {
        "tool_run_id": "tool-run-background-result",
        "tool_call_id": "call-background-result",
        "tool_name": "openai_image_generate",
        "tool_id": "openai_image_generate",
        "result_session_item_id": "item-1",
    }


def test_assistant_response_fallback_records_session_item_without_message() -> None:
    session_service = _FakeSessionRecorderPort()
    recorder = OrchestrationSessionRecorder(session_service=session_service)

    item_ids = recorder.append_assistant_response_item(
        session_key="agent:assistant:main",
        active_session_id="session-1",
        invocation_id="llm-invocation-final",
        response_text="Done.",
        structured_output={"ok": True},
        finish_reason="stop",
        usage_payload={"input_tokens": 10, "output_tokens": 2},
    )

    assert item_ids == ("item-1",)
    assert session_service.messages == []
    [item] = session_service.items
    assert item.role == "assistant"
    assert item.kind.value == "assistant_message"
    assert item.source_module == "llm"
    assert item.source_kind == "llm_invocation"
    assert item.source_id == "llm-invocation-final"
    assert item.content_payload["text"] == "Done."
    assert item.content_payload["structured_output"] == {"ok": True}
    assert item.content_payload["finish_reason"] == "stop"
    assert item.content_payload["usage"] == {
        "input_tokens": 10,
        "output_tokens": 2,
    }


def test_late_tool_run_terminal_marks_item_without_advancing_chain() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)

    with uow:
        chain = ExecutionChain.create(
            chain_id="chain-late-tool",
            turn_id="run-late-tool",
        )
        chain.increment_step_count()
        chain.wait(active_step_id="step-late-tool")
        chain.complete()
        step = ExecutionStep.create(
            step_id="step-late-tool",
            chain_id=chain.id,
            turn_id=chain.turn_id,
            step_index=0,
            kind=ExecutionStepKind.TOOL_BATCH,
            correlation_key="run-late-tool:tool-batch:invocation-1",
        )
        step.wait()
        tool_call = ExecutionStepItem.create(
            item_id="item-late-tool-call",
            step_id=step.id,
            chain_id=chain.id,
            turn_id=chain.turn_id,
            item_index=0,
            kind=ExecutionStepItemKind.TOOL_CALL,
            owner=ExecutionOwnerReference(
                owner_kind="tool_call",
                owner_id="call-late-tool",
            ),
        )
        tool_call.complete(summary_payload={"tool_name": "background_echo"})
        tool_run = ExecutionStepItem.create(
            item_id="item-late-tool-run",
            step_id=step.id,
            chain_id=chain.id,
            turn_id=chain.turn_id,
            item_index=1,
            kind=ExecutionStepItemKind.TOOL_RUN,
            owner=ExecutionOwnerReference(
                owner_kind="tool_run",
                owner_id="tool-run-late",
            ),
            correlation_key="call-late-tool",
        )
        tool_run.wait()
        uow.execution_chains.add(chain)
        uow.execution_steps.add(step)
        uow.execution_step_items.add(tool_call)
        uow.execution_step_items.add(tool_run)
        uow.commit()

    tool_run = ToolRun.create(
        run_id="tool-run-late",
        tool_id="background_echo",
        input_payload={},
        metadata={
            "source": "orchestration",
            "orchestration_run_id": "run-late-tool",
            "tool_call_id": "call-late-tool",
            "tool_name": "background_echo",
        },
        target=ToolExecutionTarget(mode=ToolMode.BACKGROUND),
    )
    tool_run.succeed(ToolRunResult.text("late done"))
    events = _FakeEventPublisher()
    coordinator = OrchestrationToolResumeCoordinator(
        uow_factory=lambda: uow,
        engine=SimpleNamespace(
            tool_execution_port=_FakeToolExecutionPort(tool_run),
        ),
        get_run=lambda _run_id: (_ for _ in ()).throw(AssertionError("no run lookup")),
        resume_run=lambda *_args: (_ for _ in ()).throw(AssertionError("no resume")),
        events_service=events,
    )

    resumed = coordinator.handle_terminal_tool_run(tool_run.id)

    query = OrchestrationRunQueryService(lambda: uow)
    assert resumed == []
    assert events.events == []
    item = query.get_execution_step_item("item-late-tool-run")
    assert item.status is ExecutionStepItemStatus.LATE_OBSERVED
    assert item.summary_payload is not None
    assert item.summary_payload["tool_run_id"] == "tool-run-late"
    assert item.summary_payload["status"] == "succeeded"
    assert item.summary_payload["tool_id"] == "background_echo"
    assert item.summary_payload["mode"] == "background"
    assert item.summary_payload["strategy"] == "async"
    assert item.summary_payload["environment"] == "local"
    assert "completed_at" in item.summary_payload
    step = query.get_execution_step("step-late-tool")
    assert step.status is ExecutionStepStatus.WAITING
    [chain] = query.list_execution_chains("run-late-tool")
    assert chain.status is ExecutionChainStatus.COMPLETED
    assert chain.active_step_id is None


def test_orchestration_owned_orphan_tool_result_publishes_operational_event() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    tool_run = ToolRun.create(
        run_id="tool-run-orphan",
        tool_id="openai_image_generate",
        function_id="openai_image_generate",
        source_id="configured.local.openai_image",
        input_payload={},
        metadata={
            "source": "orchestration",
            "orchestration_run_id": "run-orphan-tool",
            "tool_call_id": "call-orphan-tool",
            "tool_name": "openai_image_generate",
        },
        target=ToolExecutionTarget(mode=ToolMode.BACKGROUND),
    )
    tool_run.succeed(ToolRunResult.text("done"))
    events = _FakeEventPublisher()
    coordinator = OrchestrationToolResumeCoordinator(
        uow_factory=lambda: uow,
        engine=SimpleNamespace(
            tool_execution_port=_FakeToolExecutionPort(tool_run),
        ),
        get_run=lambda _run_id: (_ for _ in ()).throw(AssertionError("no run lookup")),
        resume_run=lambda *_args: (_ for _ in ()).throw(AssertionError("no resume")),
        events_service=events,
    )

    resumed = coordinator.handle_terminal_tool_run(tool_run.id)

    assert resumed == []
    assert len(events.events) == 1
    event = events.events[0]
    assert event.name == ORCHESTRATION_ORPHAN_TOOL_RESULT_OBSERVED_EVENT
    assert event.kind == "fact"
    assert event.ordering_key == tool_run.id
    assert event.payload["status"] == "orphaned"
    assert event.payload["level"] == "warning"
    assert event.payload["reason"] == "execution_step_item_not_found"
    assert event.payload["tool_run_id"] == tool_run.id
    assert event.payload["run_id"] == "run-orphan-tool"
    assert event.payload["orchestration_run_id"] == "run-orphan-tool"
    assert event.payload["tool_status"] == "succeeded"
    assert event.payload["tool_id"] == "openai_image_generate"
    assert event.payload["entity_type"] == "tool_run"
    assert event.payload["entity_id"] == tool_run.id


def test_replayed_terminal_tool_event_does_not_resume_run_twice() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    run = OrchestrationRun.accept(
        run_id="run-replayed-terminal-tool",
        inbound_instruction=InboundInstruction(source="unit", content="tool"),
        metadata={"session_key": "session-replayed-terminal-tool"},
    )
    run.bind_session(active_session_id="session-instance")
    run.enqueue(lane_key="lane-replay")
    run.claim(worker_id="worker-1")
    tool_run = ToolRun.create(
        run_id="tool-run-replayed-terminal",
        tool_id="background_echo",
        input_payload={},
        metadata={
            "source": "orchestration",
            "orchestration_run_id": run.id,
            "tool_call_id": "call-replayed-terminal",
            "tool_name": "background_echo",
        },
        target=ToolExecutionTarget(mode=ToolMode.BACKGROUND),
    )
    tool_run.succeed(ToolRunResult.text("done"))
    run.wait_on_tool(
        worker_id="worker-1",
        pending_tool_run_ids=(tool_run.id,),
        reason="tool_background_wait",
    )

    with uow:
        chain = ExecutionChain.create(
            chain_id="chain-replayed-terminal-tool",
            turn_id=run.id,
        )
        intake_step = ExecutionStep.create(
            step_id="step-replayed-terminal-intake",
            chain_id=chain.id,
            turn_id=chain.turn_id,
            step_index=0,
            kind=ExecutionStepKind.INTAKE,
            correlation_key="run-replayed-terminal-tool:0:intake",
        )
        intake_step.link_owner(
            ExecutionOwnerReference(
                owner_kind="orchestration_run",
                owner_id=run.id,
            ),
        )
        intake_step.complete()
        chain.increment_step_count()
        chain.increment_step_count()
        chain.wait(active_step_id="step-replayed-terminal-tool")
        step = ExecutionStep.create(
            step_id="step-replayed-terminal-tool",
            chain_id=chain.id,
            turn_id=chain.turn_id,
            step_index=1,
            kind=ExecutionStepKind.TOOL_BATCH,
            correlation_key="run-replayed-terminal-tool:tool-batch:llm-1",
        )
        step.wait()
        tool_call = ExecutionStepItem.create(
            item_id="item-replayed-terminal-call",
            step_id=step.id,
            chain_id=chain.id,
            turn_id=chain.turn_id,
            item_index=0,
            kind=ExecutionStepItemKind.TOOL_CALL,
            owner=ExecutionOwnerReference(
                owner_kind="tool_call",
                owner_id="call-replayed-terminal",
            ),
        )
        tool_call.complete(summary_payload={"tool_name": "background_echo"})
        tool_item = ExecutionStepItem.create(
            item_id="item-replayed-terminal-run",
            step_id=step.id,
            chain_id=chain.id,
            turn_id=chain.turn_id,
            item_index=1,
            kind=ExecutionStepItemKind.TOOL_RUN,
            owner=ExecutionOwnerReference(
                owner_kind="tool_run",
                owner_id=tool_run.id,
            ),
            correlation_key="call-replayed-terminal",
        )
        tool_item.wait()
        uow.execution_chains.add(chain)
        uow.execution_steps.add(intake_step)
        uow.execution_steps.add(step)
        uow.execution_step_items.add(tool_call)
        uow.execution_step_items.add(tool_item)
        uow.orchestration_runs.add(run)
        uow.orchestration_waits.replace_tool_waits(run.id, (tool_run.id,))
        uow.collect(chain)
        uow.collect(intake_step)
        uow.collect(step)
        uow.collect(tool_call)
        uow.collect(tool_item)
        uow.collect(run)
        uow.commit()

    query = OrchestrationRunQueryService(lambda: uow)
    wait = RunWaitCoordinator(
        uow_factory=lambda: uow,
        dispatch_port=OrchestrationDispatchAdapter(),
        engine=None,
        session_service=None,
        agent_service=None,
        get_run=query.get_run,
        resume_input_factory=lambda **kwargs: ResumeOrchestrationRunInput(**kwargs),
        grant_run_tool_authorization=lambda **_kwargs: None,
        grant_session_tool_authorization=lambda **_kwargs: None,
        grant_agent_effect_authorization=lambda **_kwargs: None,
        append_approval_resolution_message=lambda **_kwargs: None,
        reconcile_tool_waits=lambda _tool_run_ids: None,
    )
    resume_engine = _FakeBackgroundToolResumeEngine(tool_run)
    coordinator = OrchestrationToolResumeCoordinator(
        uow_factory=lambda: uow,
        engine=resume_engine,
        get_run=query.get_run,
        resume_run=wait.resume_after_tool_completion,
    )

    first = coordinator.handle_terminal_tool_run(tool_run.id)
    second = coordinator.handle_terminal_tool_run(tool_run.id)

    assert [run.id for run in first] == [run.id]
    assert second == []
    assert resume_engine.appended_run_ids == [run.id]
    resumed_run = query.get_run(run.id)
    assert resumed_run.status is not OrchestrationRunStatus.WAITING
    with uow:
        assert uow.orchestration_waits.list_run_ids_for_tool_run(tool_run.id) == []


def test_wait_coordinator_finds_existing_tool_results_from_session_items_without_message_read() -> None:
    session_service = _FakeSessionItemLookupPort(
        (
            SessionItem(
                id="session-item-tool-result",
                session_key="session:assistant",
                session_id="active-session",
                sequence_no=3,
                kind=SessionItemKind.TOOL_RESULT,
                role="tool",
                visibility=SessionItemVisibility(model_visible=True),
                content_payload={
                    "content": [{"type": "text", "text": "done"}],
                },
                source_module="tool",
                source_kind="tool_run",
                source_id="tool-run-1",
                call_id="call-1",
                tool_name="tool.echo",
            ),
        ),
    )
    wait = RunWaitCoordinator(
        uow_factory=lambda: None,
        dispatch_port=OrchestrationDispatchAdapter(),
        engine=None,
        session_service=session_service,
        agent_service=None,
        get_run=lambda _run_id: None,
        resume_input_factory=lambda **kwargs: ResumeOrchestrationRunInput(**kwargs),
        grant_run_tool_authorization=lambda **_kwargs: None,
        grant_session_tool_authorization=lambda **_kwargs: None,
        grant_agent_effect_authorization=lambda **_kwargs: None,
        append_approval_resolution_message=lambda **_kwargs: None,
        reconcile_tool_waits=lambda _tool_run_ids: None,
    )
    run = OrchestrationRun.accept(
        run_id="run-session-item-tool-result",
        inbound_instruction=InboundInstruction(source="unit", content="go"),
        metadata={"session_key": "session:assistant"},
    )
    run.bind_session(active_session_id="active-session")

    item_ids = wait._tool_result_item_ids_for_call(
        run=run,
        tool_call_id="call-1",
    )

    assert item_ids == ("session-item-tool-result",)
    assert session_service.message_reads == 0
    assert len(session_service.item_inputs) == 1
    assert session_service.item_inputs[0].model_visible is True


def test_approval_replay_and_resume_steps_are_materialized() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    uow = SqlAlchemyUnitOfWork(session_factory)
    intake = RunIntakeCoordinator(
        uow_factory=lambda: uow,
        scheduler=OrchestrationScheduler(),
        dispatch_port=OrchestrationDispatchAdapter(),
        plan_prepared_session_run=lambda _data: None,
    )
    run = intake.accept(
        AcceptOrchestrationRunInput(
            run_id="run-exec-chain-approval",
            inbound_instruction=InboundInstruction(source="unit", content="approve"),
        ),
    )
    intake.enqueue(EnqueueOrchestrationRunInput(run_id=run.id))
    request = PendingApprovalRequest(
        request_id="call-approval-1",
        effect_id="local_tool_access",
        label="Run Echo",
        tool_ids=("echo",),
        tool_name="echo",
        tool_arguments={"message": "hello"},
        execution_mode="inline",
        execution_strategy="async",
        execution_environment="local",
    )

    with uow:
        persisted = uow.orchestration_runs.get(run.id)
        assert persisted is not None
        approval_step = materialize_approval_execution_step(
            uow,
            run=persisted,
            request=request,
        )
        assert approval_step is not None
        uow.commit()

    query = OrchestrationRunQueryService(lambda: uow)
    chain = query.get_active_execution_chain(run.id)
    assert chain is not None
    steps = query.list_execution_steps(chain.id)
    assert [(step.step_index, step.kind, step.status) for step in steps] == [
        (0, ExecutionStepKind.INTAKE, ExecutionStepStatus.COMPLETED),
        (1, ExecutionStepKind.LLM, ExecutionStepStatus.CREATED),
        (2, ExecutionStepKind.APPROVAL, ExecutionStepStatus.WAITING),
    ]
    approval_item = query.find_execution_step_items_by_owner(
        ExecutionOwnerReference(
            owner_kind="approval_request",
            owner_id=request.request_id,
        ),
    )[0]
    assert approval_item.kind is ExecutionStepItemKind.APPROVAL_REQUEST
    assert approval_item.status is ExecutionStepItemStatus.WAITING

    with uow:
        persisted = uow.orchestration_runs.get(run.id)
        assert persisted is not None
        mark_approval_request_step_item_terminal(
            uow,
            request_id=request.request_id,
            decision="allow_once",
        )
        materialize_tool_batch_execution_step(
            uow,
            run=persisted,
            llm_invocation_id="invocation-approval-1",
            tool_run_links=(
                {
                    "tool_call_id": request.request_id,
                    "tool_name": "echo",
                    "tool_run_id": "tool-run-approval-1",
                    "tool_id": "echo",
                    "status": "completed",
                    "mode": "inline",
                    "strategy": "async",
                    "environment": "local",
                    "result_session_item_id": "session-item-tool-result-approval-1",
                    "background": False,
                },
            ),
        )
        materialize_resume_execution_step(
            uow,
            run=persisted,
            reason="approval_allow_once",
        )
        uow.commit()

    steps = query.list_execution_steps(chain.id)
    assert [(step.step_index, step.kind, step.status) for step in steps] == [
        (0, ExecutionStepKind.INTAKE, ExecutionStepStatus.COMPLETED),
        (1, ExecutionStepKind.LLM, ExecutionStepStatus.CREATED),
        (2, ExecutionStepKind.APPROVAL, ExecutionStepStatus.COMPLETED),
        (3, ExecutionStepKind.TOOL_BATCH, ExecutionStepStatus.COMPLETED),
        (4, ExecutionStepKind.TOOL_RESUME, ExecutionStepStatus.COMPLETED),
    ]
    approval_item = query.find_execution_step_items_by_owner(
        ExecutionOwnerReference(
            owner_kind="approval_request",
            owner_id=request.request_id,
        ),
    )[0]
    assert approval_item.summary_payload["decision"] == "allow_once"
    tool_items = query.find_execution_step_items_by_owner(
        ExecutionOwnerReference(owner_kind="tool_call", owner_id=request.request_id),
    )
    assert [item.kind for item in tool_items] == [ExecutionStepItemKind.TOOL_CALL]
    assert tool_items[0].correlation_key == request.request_id
    [tool_run_item] = query.find_execution_step_items_by_owner(
        ExecutionOwnerReference(
            owner_kind="tool_run",
            owner_id="tool-run-approval-1",
        ),
    )
    assert tool_run_item.correlation_key == request.request_id
    chain = query.get_active_execution_chain(run.id)
    assert chain is not None
    assert chain.status is ExecutionChainStatus.RUNNING
    assert chain.active_step_id == steps[-1].id
