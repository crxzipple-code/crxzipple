from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol

from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.orchestration.application.lease_manager import (
    OrchestrationLeaseManager,
)
from crxzipple.modules.orchestration.application.execution_chain_lifecycle import (
    cancel_active_execution_step,
    complete_execution_chain,
    complete_llm_execution_step,
    current_dispatch_task_id,
    fail_active_execution_step,
    materialize_final_response_execution_step,
    materialize_tool_batch_execution_step,
    require_current_dispatch_task_id,
    start_llm_execution_step,
)
from crxzipple.modules.orchestration.application.ports import OrchestrationDispatchPort
from crxzipple.modules.orchestration.domain import (
    ExecutionChainRepository,
    ExecutionStepItemRepository,
    ExecutionStepRepository,
    OrchestrationRun,
    OrchestrationRunRepository,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    OrchestrationRunWaitRepository,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.shared.domain.aggregates import AggregateRoot

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.commands import (
        AdvanceAssignmentInput,
        CompleteAssignmentInput,
        FailAssignmentInput,
    )


class ProgressCoordinatorUnitOfWork(Protocol):
    execution_chains: ExecutionChainRepository
    execution_steps: ExecutionStepRepository
    execution_step_items: ExecutionStepItemRepository
    orchestration_runs: OrchestrationRunRepository
    orchestration_waits: OrchestrationRunWaitRepository
    dispatch_tasks: DispatchTaskRepository

    def __enter__(self) -> "ProgressCoordinatorUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...

    def commit(self) -> None:
        ...


@dataclass(slots=True)
class RunProgressCoordinator:
    uow_factory: Callable[[], ProgressCoordinatorUnitOfWork]
    dispatch_port: OrchestrationDispatchPort
    lease_manager: OrchestrationLeaseManager
    advance_once: Callable[[str, str], OrchestrationRun]
    heartbeat_assignment: Callable[[str, str], OrchestrationRun]
    get_run: Callable[[str], OrchestrationRun]
    apply_compaction_summary: Callable[[OrchestrationRun], None]
    maybe_request_auto_compaction: Callable[[OrchestrationRun], OrchestrationRun | None]
    clear_pending_compaction_marker: Callable[[OrchestrationRun], None]
    clear_pending_memory_flush_marker: Callable[[OrchestrationRun], None]
    is_compaction_run: Callable[[OrchestrationRun], bool]
    is_memory_flush_run: Callable[[OrchestrationRun], bool]
    advance_once_async: Callable[[str, str], Awaitable[OrchestrationRun]] | None = None

    def process_next_assigned_assignment(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> OrchestrationRun | None:
        run = self.next_assigned_assignment(
            worker_id=worker_id,
            exclude_run_ids=exclude_run_ids,
        )
        if run is None:
            return None
        return self.process_assigned_assignment(run_id=run.id, worker_id=worker_id)

    def next_assigned_assignment(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> OrchestrationRun | None:
        with self.uow_factory() as uow:
            return uow.orchestration_runs.find_next_assigned(
                worker_id=worker_id,
                exclude_run_ids=exclude_run_ids,
            )

    def process_assigned_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            if run.status is not OrchestrationRunStatus.RUNNING:
                return run
            if run.worker_id != worker_id:
                raise OrchestrationValidationError(
                    f"Orchestration run '{run_id}' is assigned to another executor.",
                )
        with self.lease_manager.heartbeat_while_processing(
            run_id=run.id,
            worker_id=worker_id,
            heartbeat_assignment=self.heartbeat_assignment,
        ):
            return self.advance_once(run_id=run.id, worker_id=worker_id)

    async def process_assigned_assignment_async(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        if self.advance_once_async is None:
            return self.process_assigned_assignment(run_id=run_id, worker_id=worker_id)
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            if run.status is not OrchestrationRunStatus.RUNNING:
                return run
            if run.worker_id != worker_id:
                raise OrchestrationValidationError(
                    f"Orchestration run '{run_id}' is assigned to another executor.",
                )
        with self.lease_manager.heartbeat_while_processing(
            run_id=run.id,
            worker_id=worker_id,
            heartbeat_assignment=self.heartbeat_assignment,
        ):
            return await self.advance_once_async(run.id, worker_id)

    def advance_assignment(self, data: "AdvanceAssignmentInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.advance(
                worker_id=data.worker_id,
                stage=data.stage,
                step_increment=data.step_increment,
                metadata=data.metadata,
                happened_at=data.now,
            )
            if data.stage is OrchestrationRunStage.LLM:
                start_llm_execution_step(
                    uow,
                    run=run,
                    dispatch_task_id=require_current_dispatch_task_id(uow, run=run),
                )
            if data.stage is OrchestrationRunStage.TOOL:
                combined_payload = {
                    **data.metadata,
                    **data.execution_payload,
                }
                llm_invocation_id = data.execution_payload.get("llm_invocation_id")
                if isinstance(llm_invocation_id, str):
                    complete_llm_execution_step(
                        uow,
                        run=run,
                        llm_invocation_id=llm_invocation_id,
                        assistant_progress_message_ids=_assistant_progress_message_ids(
                            combined_payload,
                        ),
                        summary_payload=_llm_step_summary(combined_payload),
                    )
                    materialize_tool_batch_execution_step(
                        uow,
                        run=run,
                        llm_invocation_id=llm_invocation_id,
                        tool_run_links=_tool_run_links(data.execution_payload),
                    )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def complete_assignment(self, data: "CompleteAssignmentInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            if data.metadata:
                run.metadata.update(data.metadata)
            combined_payload = {
                **data.metadata,
                **data.result_payload,
                **data.execution_payload,
            }
            llm_invocation_id = data.execution_payload.get("llm_invocation_id")
            if isinstance(llm_invocation_id, str):
                complete_llm_execution_step(
                    uow,
                    run=run,
                    llm_invocation_id=llm_invocation_id,
                    assistant_progress_message_ids=_assistant_progress_message_ids(
                        combined_payload,
                    ),
                    summary_payload=_llm_step_summary(combined_payload),
                )
                materialize_tool_batch_execution_step(
                    uow,
                    run=run,
                    llm_invocation_id=llm_invocation_id,
                    tool_run_links=_tool_run_links(data.execution_payload),
                )
            materialize_final_response_execution_step(
                uow,
                run=run,
                llm_invocation_id=(
                    llm_invocation_id if isinstance(llm_invocation_id, str) else None
                ),
                assistant_message_ids=_assistant_message_ids(combined_payload),
                summary_payload=_final_response_summary(combined_payload),
            )
            dispatch_task_id = require_current_dispatch_task_id(uow, run=run)
            complete_execution_chain(uow, run=run)
            run.complete(
                worker_id=data.worker_id,
                result_payload=data.result_payload,
                happened_at=data.now,
            )
            self.dispatch_port.complete(
                uow.dispatch_tasks,
                uow,
                run,
                dispatch_task_id=dispatch_task_id,
            )
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
        self.apply_compaction_summary(run)
        self.maybe_request_auto_compaction(run)
        if self.is_compaction_run(run):
            self.clear_pending_compaction_marker(run)
        if self.is_memory_flush_run(run):
            self.clear_pending_memory_flush_marker(run)
        return self.get_run(data.run_id)

    def fail_assignment(self, data: "FailAssignmentInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            dispatch_task_id = require_current_dispatch_task_id(uow, run=run)
            fail_active_execution_step(
                uow,
                run=run,
                message=data.message,
                code=data.code,
                details=data.details,
            )
            run.fail(
                worker_id=data.worker_id,
                message=data.message,
                code=data.code,
                details=data.details,
                happened_at=data.now,
            )
            self.dispatch_port.fail(
                uow.dispatch_tasks,
                uow,
                run,
                dispatch_task_id=dispatch_task_id,
            )
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
        if self.is_compaction_run(run):
            self.clear_pending_compaction_marker(run)
        if self.is_memory_flush_run(run):
            self.clear_pending_memory_flush_marker(run)
        return run

    def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
    ) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            cancel_active_execution_step(uow, run=run)
            run.cancel(reason=reason)
            dispatch_task_id = current_dispatch_task_id(uow, run=run)
            if dispatch_task_id is not None:
                self.dispatch_port.cancel(
                    uow.dispatch_tasks,
                    uow,
                    run,
                    dispatch_task_id=dispatch_task_id,
                )
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
        if self.is_compaction_run(run):
            self.clear_pending_compaction_marker(run)
        if self.is_memory_flush_run(run):
            self.clear_pending_memory_flush_marker(run)
        return run

    @staticmethod
    def _get_run(
        uow: ProgressCoordinatorUnitOfWork,
        run_id: str,
    ) -> OrchestrationRun:
        run = uow.orchestration_runs.get(run_id)
        if run is None:
            raise OrchestrationRunNotFoundError(
                f"Orchestration run '{run_id}' was not found.",
            )
        return run


def _llm_step_summary(payload: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in (
        "assistant_progress_message_ids",
        "assistant_message_id",
        "assistant_message_ids",
        "context_render_snapshot_id",
        "llm_id",
        "llm_transcript_consumption",
        "prompt_mode",
        "tool_call_message_ids",
        "tool_call_names",
        "tool_result_message_ids",
        "user_message_id",
    ):
        value = payload.get(key)
        if value is not None:
            summary[key] = value
    progress_text = payload.get("assistant_progress_text")
    if isinstance(progress_text, str) and progress_text.strip():
        summary["assistant_progress_text"] = progress_text
        summary["assistant_progress_text_chars"] = len(progress_text)
    return summary


def _tool_run_links(payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    raw_links = payload.get("tool_run_links")
    if not isinstance(raw_links, (list, tuple)):
        return ()
    links: list[dict[str, object]] = []
    for raw_link in raw_links:
        if isinstance(raw_link, dict):
            links.append(dict(raw_link))
    return tuple(links)


def _assistant_message_ids(payload: dict[str, object]) -> tuple[str, ...]:
    message_ids: list[str] = []
    raw_ids = payload.get("assistant_message_ids")
    if isinstance(raw_ids, (list, tuple)):
        for item in raw_ids:
            if isinstance(item, str) and item.strip():
                message_ids.append(item.strip())
    raw_id = payload.get("assistant_message_id")
    if isinstance(raw_id, str) and raw_id.strip():
        normalized = raw_id.strip()
        if normalized not in message_ids:
            message_ids.append(normalized)
    return tuple(message_ids)


def _assistant_progress_message_ids(payload: dict[str, object]) -> tuple[str, ...]:
    message_ids: list[str] = []
    raw_ids = payload.get("assistant_progress_message_ids")
    if isinstance(raw_ids, (list, tuple)):
        for item in raw_ids:
            if isinstance(item, str) and item.strip():
                normalized = item.strip()
                if normalized not in message_ids:
                    message_ids.append(normalized)
    return tuple(message_ids)


def _final_response_summary(payload: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in (
        "assistant_message_id",
        "assistant_message_ids",
        "context_render_snapshot_id",
        "llm_id",
        "llm_invocation_id",
        "prompt_mode",
        "tool_result_message_ids",
        "user_message_id",
    ):
        value = payload.get(key)
        if value is not None:
            summary[key] = value
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        summary["output_text_chars"] = len(output_text)
    return summary
