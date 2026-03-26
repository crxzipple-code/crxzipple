from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from crxzipple.modules.memory.domain.entities import MemoryCandidate, MemoryEntry
from crxzipple.modules.memory.domain.value_objects import MemoryCandidateStatus
from crxzipple.modules.memory.infrastructure.persistence.models import (
    MemoryCandidateModel,
    MemoryEntryModel,
)


class SqlAlchemyMemoryCandidateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, candidate: MemoryCandidate) -> None:
        self.session.merge(
            MemoryCandidateModel(
                id=candidate.id,
                agent_id=candidate.agent_id,
                session_key=candidate.session_key,
                run_id=candidate.run_id,
                title=candidate.title,
                content=candidate.content,
                summary=candidate.summary,
                tags_payload=list(candidate.tags),
                metadata_payload=dict(candidate.metadata),
                status=candidate.status.value,
                created_at=candidate.created_at,
                reviewed_at=candidate.reviewed_at,
                review_reason=candidate.review_reason,
                approved_entry_id=candidate.approved_entry_id,
            ),
        )

    def get(self, candidate_id: str) -> MemoryCandidate | None:
        model = self.session.get(MemoryCandidateModel, candidate_id)
        if model is None:
            return None
        return self._to_entity(model)

    def list(
        self,
        *,
        agent_id: str | None = None,
        session_key: str | None = None,
        run_id: str | None = None,
        status: MemoryCandidateStatus | None = None,
        limit: int | None = None,
    ) -> list[MemoryCandidate]:
        statement = select(MemoryCandidateModel)
        if agent_id is not None:
            statement = statement.where(MemoryCandidateModel.agent_id == agent_id.strip())
        if session_key is not None:
            statement = statement.where(
                MemoryCandidateModel.session_key == session_key.strip(),
            )
        if run_id is not None:
            statement = statement.where(MemoryCandidateModel.run_id == run_id.strip())
        if status is not None:
            statement = statement.where(MemoryCandidateModel.status == status.value)
        statement = statement.order_by(
            MemoryCandidateModel.created_at.desc(),
            MemoryCandidateModel.id.desc(),
        )
        if limit is not None and limit > 0:
            statement = statement.limit(limit)
        models = self.session.scalars(statement).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: MemoryCandidateModel) -> MemoryCandidate:
        return MemoryCandidate(
            id=model.id,
            agent_id=model.agent_id,
            session_key=model.session_key,
            run_id=model.run_id,
            title=model.title,
            content=model.content,
            summary=model.summary,
            tags=tuple(model.tags_payload or ()),
            metadata=(
                dict(model.metadata_payload)
                if isinstance(model.metadata_payload, dict)
                else {}
            ),
            status=MemoryCandidateStatus(model.status),
            created_at=model.created_at,
            reviewed_at=model.reviewed_at,
            review_reason=model.review_reason,
            approved_entry_id=model.approved_entry_id,
        )


class SqlAlchemyMemoryEntryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entry: MemoryEntry) -> None:
        self.session.merge(
            MemoryEntryModel(
                id=entry.id,
                agent_id=entry.agent_id,
                session_key=entry.session_key,
                run_id=entry.run_id,
                source_candidate_id=entry.source_candidate_id,
                title=entry.title,
                content=entry.content,
                summary=entry.summary,
                tags_payload=list(entry.tags),
                metadata_payload=dict(entry.metadata),
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            ),
        )

    def delete(self, entry_id: str) -> None:
        model = self.session.get(MemoryEntryModel, entry_id)
        if model is not None:
            self.session.delete(model)

    def get(self, entry_id: str) -> MemoryEntry | None:
        model = self.session.get(MemoryEntryModel, entry_id)
        if model is None:
            return None
        return self._to_entity(model)

    def list(
        self,
        *,
        agent_id: str | None = None,
        query: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryEntry]:
        statement = select(MemoryEntryModel)
        if agent_id is not None:
            statement = statement.where(MemoryEntryModel.agent_id == agent_id.strip())
        if query is not None and query.strip():
            pattern = f"%{query.strip()}%"
            statement = statement.where(
                or_(
                    MemoryEntryModel.title.ilike(pattern),
                    MemoryEntryModel.content.ilike(pattern),
                    MemoryEntryModel.summary.ilike(pattern),
                ),
            )
        statement = statement.order_by(
            MemoryEntryModel.created_at.desc(),
            MemoryEntryModel.id.desc(),
        )
        if limit is not None and limit > 0:
            statement = statement.limit(limit)
        models = self.session.scalars(statement).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: MemoryEntryModel) -> MemoryEntry:
        return MemoryEntry(
            id=model.id,
            agent_id=model.agent_id,
            session_key=model.session_key,
            run_id=model.run_id,
            source_candidate_id=model.source_candidate_id,
            title=model.title,
            content=model.content,
            summary=model.summary,
            tags=tuple(model.tags_payload or ()),
            metadata=(
                dict(model.metadata_payload)
                if isinstance(model.metadata_payload, dict)
                else {}
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
