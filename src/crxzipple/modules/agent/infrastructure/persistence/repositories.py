from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.domain.value_objects import (
    AgentExecutionPolicy,
    AgentIdentity,
    AgentInstructionPolicy,
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.modules.agent.infrastructure.persistence.models import AgentProfileModel


class SqlAlchemyAgentProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, profile: AgentProfile) -> None:
        self.session.merge(
            AgentProfileModel(
                id=profile.id,
                name=profile.name,
                description=profile.description,
                enabled=profile.enabled,
                identity_payload=profile.identity.to_payload(),
                instruction_policy_payload=profile.instruction_policy.to_payload(),
                llm_routing_policy_payload=profile.llm_routing_policy.to_payload(),
                execution_policy_payload=profile.execution_policy.to_payload(),
                runtime_preferences_payload=profile.runtime_preferences.to_payload(),
            ),
        )

    def get(self, profile_id: str) -> AgentProfile | None:
        model = self.session.get(AgentProfileModel, profile_id)
        if model is None:
            return None
        return self._to_entity(model)

    def list(self) -> list[AgentProfile]:
        models = self.session.scalars(
            select(AgentProfileModel).order_by(AgentProfileModel.id),
        ).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: AgentProfileModel) -> AgentProfile:
        return AgentProfile(
            id=model.id,
            name=model.name,
            description=model.description,
            enabled=model.enabled,
            identity=AgentIdentity.from_payload(model.identity_payload),
            instruction_policy=AgentInstructionPolicy.from_payload(
                model.instruction_policy_payload,
            ),
            llm_routing_policy=AgentLlmRoutingPolicy.from_payload(
                model.llm_routing_policy_payload,
            ),
            execution_policy=AgentExecutionPolicy.from_payload(
                model.execution_policy_payload,
            ),
            runtime_preferences=AgentRuntimePreferences.from_payload(
                model.runtime_preferences_payload,
            ),
        )
