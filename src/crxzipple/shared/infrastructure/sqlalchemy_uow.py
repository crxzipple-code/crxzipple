from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from crxzipple.core.db import SessionFactory
from crxzipple.core.logger import get_logger
from crxzipple.modules.dispatch.infrastructure.persistence.repositories import (
    SqlAlchemyDispatchTaskRepository,
)
from crxzipple.modules.llm.infrastructure.persistence.repositories import (
    SqlAlchemyLlmInvocationRepository,
    SqlAlchemyLlmProfileRepository,
)
from crxzipple.modules.orchestration.infrastructure.persistence.repositories import (
    SqlAlchemyOrchestrationExecutorLeaseRepository,
    SqlAlchemyOrchestrationIngressRequestRepository,
    SqlAlchemyOrchestrationRunRepository,
    SqlAlchemyOrchestrationSchedulerSignalRepository,
    SqlAlchemyOrchestrationRunWaitRepository,
)
from crxzipple.modules.session.infrastructure.persistence.repositories import (
    SqlAlchemySessionMessageRepository,
    SqlAlchemySessionInstanceRepository,
    SqlAlchemySessionRepository,
)
from crxzipple.modules.tool.infrastructure.persistence.repositories import (
    SqlAlchemyToolFunctionCatalogRepository,
    SqlAlchemyToolFunctionRepository,
    SqlAlchemyToolProviderBackendRepository,
    SqlAlchemyToolRunAssignmentRepository,
    SqlAlchemyToolRunRepository,
    SqlAlchemyToolSourceDiscoveryRunRepository,
    SqlAlchemyToolSourceRepository,
    SqlAlchemyToolWorkerRepository,
)
from crxzipple.shared.application.unit_of_work import UnitOfWork
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.infrastructure.event_bus import EventBus

logger = get_logger(__name__)


class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session_factory: SessionFactory, event_bus: EventBus) -> None:
        self._session_factory = session_factory
        self._event_bus = event_bus
        self._session: Session | None = None
        self._seen: list[AggregateRoot[Any]] = []

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._session_factory()
        self.dispatch_tasks = SqlAlchemyDispatchTaskRepository(self.session)
        self.tool_sources = SqlAlchemyToolSourceRepository(self.session)
        self.tool_source_discovery_runs = SqlAlchemyToolSourceDiscoveryRunRepository(
            self.session,
        )
        self.tool_functions = SqlAlchemyToolFunctionRepository(self.session)
        self.tool_function_catalog = SqlAlchemyToolFunctionCatalogRepository(
            self.session,
        )
        self.tool_provider_backends = SqlAlchemyToolProviderBackendRepository(
            self.session,
        )
        self.tool_runs = SqlAlchemyToolRunRepository(self.session)
        self.tool_run_assignments = SqlAlchemyToolRunAssignmentRepository(
            self.session,
        )
        self.tool_workers = SqlAlchemyToolWorkerRepository(self.session)
        self.sessions = SqlAlchemySessionRepository(self.session)
        self.session_messages = SqlAlchemySessionMessageRepository(self.session)
        self.session_instances = SqlAlchemySessionInstanceRepository(self.session)
        self.llm_profiles = SqlAlchemyLlmProfileRepository(self.session)
        self.llm_invocations = SqlAlchemyLlmInvocationRepository(self.session)
        self.llms = self.llm_profiles
        self.orchestration_runs = SqlAlchemyOrchestrationRunRepository(self.session)
        self.orchestration_ingress_requests = (
            SqlAlchemyOrchestrationIngressRequestRepository(self.session)
        )
        self.orchestration_scheduler_signals = (
            SqlAlchemyOrchestrationSchedulerSignalRepository(self.session)
        )
        self.orchestration_executor_leases = (
            SqlAlchemyOrchestrationExecutorLeaseRepository(self.session)
        )
        self.orchestration_waits = SqlAlchemyOrchestrationRunWaitRepository(
            self.session,
        )
        self._seen = []
        logger.debug("opened unit of work")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        if self._session is None:
            return

        if exc is not None:
            self.rollback()

        self._session.close()
        logger.debug("closed unit of work")
        self._session = None
        self._seen = []

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork session requested outside of context manager")
        return self._session

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        if aggregate not in self._seen:
            self._seen.append(aggregate)
            logger.debug(
                "tracked aggregate in unit of work",
                extra={"aggregate_type": type(aggregate).__name__, "aggregate_id": aggregate.id},
            )

    def flush(self) -> None:
        logger.debug("flushing unit of work")
        self.session.flush()

    def commit(self) -> None:
        logger.debug("committing unit of work", extra={"aggregate_count": len(self._seen)})
        self.session.commit()
        events = tuple(
            event
            for aggregate in self._seen
            for event in aggregate.pull_events()
        )
        if events:
            self._event_bus.publish_many(events)
        self._seen.clear()

    def rollback(self) -> None:
        logger.warning("rolling back unit of work")
        self.session.rollback()
        self._seen.clear()
