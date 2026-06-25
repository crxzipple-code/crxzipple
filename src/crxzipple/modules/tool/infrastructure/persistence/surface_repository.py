from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.tool.application.surface import ToolSurface
from crxzipple.modules.tool.infrastructure.persistence.models import ToolSurfaceModel
from crxzipple.modules.tool.infrastructure.persistence.repository_payloads import (
    dict_payload,
)
from crxzipple.modules.tool.infrastructure.persistence.repository_surface_payloads import (
    tool_surface_from_payload,
)
from crxzipple.shared.time import coerce_utc_datetime


class SqlAlchemyToolSurfaceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolSurfaceModel] = {}

    def add(self, surface: ToolSurface) -> None:
        model = self._loaded_models.get(surface.surface_id)
        if model is None:
            model = self.session.get(ToolSurfaceModel, surface.surface_id)
        if model is None:
            model = self._to_model(surface)
            self.session.add(model)
        else:
            self._apply_to_model(model, surface)
        self._loaded_models[surface.surface_id] = model

    def get(self, surface_id: str) -> ToolSurface | None:
        model = self.session.get(ToolSurfaceModel, surface_id)
        if model is None:
            return None
        self._loaded_models[model.surface_id] = model
        return self._to_entity(model)

    def list_for_run(self, run_id: str) -> list[ToolSurface]:
        models = self.session.scalars(
            select(ToolSurfaceModel)
            .where(ToolSurfaceModel.run_id == run_id)
            .order_by(ToolSurfaceModel.created_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.surface_id] = model
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_model(surface: ToolSurface) -> ToolSurfaceModel:
        return ToolSurfaceModel(**SqlAlchemyToolSurfaceRepository._to_mapping(surface))

    @staticmethod
    def _to_mapping(surface: ToolSurface) -> dict[str, object]:
        return {
            "surface_id": surface.surface_id,
            "session_id": surface.session_id,
            "run_id": surface.run_id,
            "agent_id": surface.agent_id,
            "policy_version": surface.policy_version,
            "surface_payload": surface.to_payload(),
            "estimate_payload": dict(surface.estimate),
            "diagnostics_payload": dict(surface.diagnostics),
            "created_at": surface.created_at,
        }

    @staticmethod
    def _apply_to_model(model: ToolSurfaceModel, surface: ToolSurface) -> None:
        mapping = SqlAlchemyToolSurfaceRepository._to_mapping(surface)
        for key, value in mapping.items():
            setattr(model, key, value)

    @staticmethod
    def _to_entity(model: ToolSurfaceModel) -> ToolSurface:
        payload = dict_payload(model.surface_payload)
        return tool_surface_from_payload(
            payload,
            fallback_surface_id=model.surface_id,
            fallback_created_at=coerce_utc_datetime(model.created_at),
        )
