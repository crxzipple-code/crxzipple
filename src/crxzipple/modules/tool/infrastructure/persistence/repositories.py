from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.tool.application.catalog_models import (
    ToolFunctionCatalogRecord,
    ToolFunctionRequirements,
    ToolSourceDiscoveryRunRecord,
)
from crxzipple.modules.tool.domain.entities import (
    ToolFunction,
    ToolProviderBackend,
    ToolRun,
    ToolRunAssignment,
    ToolSource,
    ToolWorkerRegistration,
)
from crxzipple.modules.tool.domain.value_objects import (
    ToolCatalogSourceKind,
    ToolEnvironment,
    ToolFunctionRuntimeKind,
    ToolFunctionStatus,
    ToolRunAssignmentStatus,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolExecutionTarget,
    ToolMode,
    ToolProviderBackendStatus,
    ToolProviderCapability,
    ToolRunStatus,
    ToolSourceStatus,
    ToolWorkerStatus,
)
from crxzipple.modules.tool.infrastructure.persistence.models import (
    ToolFunctionModel,
    ToolProviderBackendModel,
    ToolRunAssignmentModel,
    ToolRunModel,
    ToolSourceDiscoveryRunModel,
    ToolSourceModel,
    ToolWorkerModel,
)
from crxzipple.shared.time import (
    coerce_utc_datetime,
    coerce_optional_utc_datetime,
)
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
    AccessSetupFlowHint,
    AccessSetupFlowKind,
)


def _enum_filter_value(value: object | None) -> str | None:
    if value is None:
        return None
    raw_value = getattr(value, "value", value)
    return str(raw_value)


def _dict_payload(value: object | None) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _dict_tuple_payload(value: object | None) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


def _string_tuple_payload(value: object | None) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(
        dict.fromkeys(
            str(item).strip()
            for item in value
            if str(item).strip()
        ),
    )


def _stable_json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: _stable_json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _stable_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_stable_json_value(item) for item in value]
    return value


def _credential_requirement_set_payload(
    requirement_set: AccessCredentialRequirementSet,
) -> dict[str, object]:
    payload = _stable_json_value(requirement_set)
    assert isinstance(payload, dict)
    return payload


def _credential_requirement_sets_to_payload(
    requirement_sets: tuple[AccessCredentialRequirementSet, ...],
) -> list[object]:
    return [
        _credential_requirement_set_payload(requirement_set)
        for requirement_set in requirement_sets
    ]


def _credential_requirement_sets_from_payload(
    payload: object | None,
) -> tuple[AccessCredentialRequirementSet, ...]:
    if not isinstance(payload, list | tuple):
        return ()
    requirement_sets: list[AccessCredentialRequirementSet] = []
    for item in payload:
        if isinstance(item, Mapping):
            requirement_sets.append(_credential_requirement_set_from_payload(item))
    return tuple(requirement_sets)


def _credential_requirement_set_from_payload(
    payload: Mapping[str, Any],
) -> AccessCredentialRequirementSet:
    consumer = _consumer_ref_from_payload(payload.get("consumer"))
    raw_requirements = payload.get("requirements")
    requirements: list[AccessCredentialRequirementDeclaration] = []
    if isinstance(raw_requirements, list | tuple):
        for item in raw_requirements:
            if isinstance(item, Mapping):
                requirements.append(
                    _credential_requirement_from_payload(item, default_consumer=consumer),
                )
    return AccessCredentialRequirementSet(
        requirement_set_id=str(payload.get("requirement_set_id", "")).strip(),
        consumer=consumer,
        requirements=tuple(requirements),
        alternative=bool(payload.get("alternative", False)),
        metadata=_dict_payload(payload.get("metadata")),
    )


def _credential_requirement_from_payload(
    payload: Mapping[str, Any],
    *,
    default_consumer: AccessConsumerRef,
) -> AccessCredentialRequirementDeclaration:
    slot_payload = payload.get("slot") if isinstance(payload.get("slot"), Mapping) else {}
    setup_payload = (
        payload.get("setup_flow_hint")
        if isinstance(payload.get("setup_flow_hint"), Mapping)
        else {}
    )
    assert isinstance(slot_payload, Mapping)
    assert isinstance(setup_payload, Mapping)
    return AccessCredentialRequirementDeclaration(
        requirement_id=str(payload.get("requirement_id", "")).strip(),
        consumer=(
            _consumer_ref_from_payload(payload.get("consumer"))
            if isinstance(payload.get("consumer"), Mapping)
            else default_consumer
        ),
        slot=AccessCredentialSlotRef(
            slot=str(slot_payload.get("slot", "")).strip(),
            expected_kind=AccessCredentialKind(
                str(slot_payload.get("expected_kind", AccessCredentialKind.API_KEY.value)),
            ),
            binding_id=(
                str(slot_payload["binding_id"]).strip()
                if slot_payload.get("binding_id") is not None
                else None
            ),
            required=bool(slot_payload.get("required", True)),
            display_name=(
                str(slot_payload["display_name"]).strip()
                if slot_payload.get("display_name") is not None
                else None
            ),
            scopes=tuple(
                str(item).strip()
                for item in slot_payload.get("scopes", ())
                if str(item).strip()
            ),
            metadata=_dict_payload(slot_payload.get("metadata")),
        ),
        provider=(
            str(payload["provider"]).strip()
            if payload.get("provider") is not None
            else None
        ),
        transport=AccessCredentialTransport(
            str(
                payload.get(
                    "transport",
                    AccessCredentialTransport.RUNTIME_CONTEXT.value,
                ),
            ),
        ),
        parameter_name=(
            str(payload["parameter_name"]).strip()
            if payload.get("parameter_name") is not None
            else None
        ),
        setup_flow_hint=AccessSetupFlowHint(
            flow_kind=AccessSetupFlowKind(
                str(setup_payload.get("flow_kind", AccessSetupFlowKind.NONE.value)),
            ),
            provider=(
                str(setup_payload["provider"]).strip()
                if setup_payload.get("provider") is not None
                else None
            ),
            authorization_url=(
                str(setup_payload["authorization_url"]).strip()
                if setup_payload.get("authorization_url") is not None
                else None
            ),
            token_url=(
                str(setup_payload["token_url"]).strip()
                if setup_payload.get("token_url") is not None
                else None
            ),
            device_code_url=(
                str(setup_payload["device_code_url"]).strip()
                if setup_payload.get("device_code_url") is not None
                else None
            ),
            callback_url=(
                str(setup_payload["callback_url"]).strip()
                if setup_payload.get("callback_url") is not None
                else None
            ),
            metadata=_dict_payload(setup_payload.get("metadata")),
        ),
        metadata=_dict_payload(payload.get("metadata")),
    )


def _consumer_ref_from_payload(payload: object | None) -> AccessConsumerRef:
    if not isinstance(payload, Mapping):
        payload = {}
    return AccessConsumerRef(
        consumer_id=str(payload.get("consumer_id", "")).strip(),
        module=str(payload.get("module", "")).strip(),
        component=(
            str(payload["component"]).strip()
            if payload.get("component") is not None
            else None
        ),
        runtime_ref=(
            str(payload["runtime_ref"]).strip()
            if payload.get("runtime_ref") is not None
            else None
        ),
        metadata=_dict_payload(payload.get("metadata")),
    )


def _execution_support_to_payload(
    execution_support: ToolExecutionSupport,
) -> dict[str, object]:
    return {
        "supported_modes": [
            mode.value for mode in execution_support.supported_modes
        ],
        "supported_strategies": [
            strategy.value
            for strategy in execution_support.supported_strategies
        ],
        "supported_environments": [
            environment.value
            for environment in execution_support.supported_environments
        ],
    }


def _execution_support_from_payload(payload: object | None) -> ToolExecutionSupport:
    if not isinstance(payload, dict):
        return ToolExecutionSupport()
    return ToolExecutionSupport(
        supported_modes=tuple(
            ToolMode(value)
            for value in payload.get("supported_modes", (ToolMode.INLINE.value,))
        ),
        supported_strategies=tuple(
            ToolExecutionStrategy(value)
            for value in payload.get(
                "supported_strategies",
                (ToolExecutionStrategy.ASYNC.value,),
            )
        ),
        supported_environments=tuple(
            ToolEnvironment(value)
            for value in payload.get(
                "supported_environments",
                (ToolEnvironment.LOCAL.value,),
            )
        ),
    )


class SqlAlchemyToolSourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolSourceModel] = {}

    def upsert(self, source: ToolSource) -> None:
        model = self._loaded_models.get(source.id)
        if model is None:
            model = self.session.get(ToolSourceModel, source.id)
        if model is None:
            model = self._to_model(source)
            self.session.add(model)
        else:
            self._apply_to_model(model, source)
        self._loaded_models[source.id] = model

    def get(self, source_id: str) -> ToolSource | None:
        model = self.session.get(ToolSourceModel, source_id)
        if model is None:
            return None
        self._loaded_models[source_id] = model
        return self._to_entity(model)

    def list(
        self,
        *,
        kind: ToolCatalogSourceKind | str | None = None,
        status: ToolSourceStatus | str | None = None,
    ) -> list[ToolSource]:
        statement = select(ToolSourceModel)
        kind_value = _enum_filter_value(kind)
        if kind_value is not None:
            statement = statement.where(ToolSourceModel.kind == kind_value)
        status_value = _enum_filter_value(status)
        if status_value is not None:
            statement = statement.where(ToolSourceModel.status == status_value)
        models = self.session.scalars(
            statement.order_by(ToolSourceModel.updated_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.source_id] = model
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_model(source: ToolSource) -> ToolSourceModel:
        return ToolSourceModel(**SqlAlchemyToolSourceRepository._to_mapping(source))

    @staticmethod
    def _to_mapping(source: ToolSource) -> dict[str, object]:
        return {
            "source_id": source.source_id,
            "kind": source.kind.value,
            "display_name": source.display_name,
            "description": source.description,
            "config_payload": dict(source.config),
            "credential_requirements_payload": [
                dict(requirement)
                for requirement in source.credential_requirements
            ],
            "runtime_requirements_payload": [
                dict(requirement)
                for requirement in source.runtime_requirements
            ],
            "status": source.status.value,
            "revision": source.revision,
            "config_hash": source.config_hash,
            "last_discovered_at": source.last_discovered_at,
            "last_discovery_status": source.last_discovery_status,
            "created_at": source.created_at,
            "updated_at": source.updated_at,
        }

    @staticmethod
    def _apply_to_model(model: ToolSourceModel, source: ToolSource) -> None:
        mapping = SqlAlchemyToolSourceRepository._to_mapping(source)
        for key, value in mapping.items():
            setattr(model, key, value)

    @staticmethod
    def _to_entity(model: ToolSourceModel) -> ToolSource:
        return ToolSource(
            id=model.source_id,
            kind=ToolCatalogSourceKind(model.kind),
            display_name=model.display_name,
            description=model.description,
            config=_dict_payload(model.config_payload),
            credential_requirements=_dict_tuple_payload(
                model.credential_requirements_payload,
            ),
            runtime_requirements=_dict_tuple_payload(
                model.runtime_requirements_payload,
            ),
            status=ToolSourceStatus(model.status),
            revision=model.revision,
            config_hash=model.config_hash,
            last_discovered_at=coerce_optional_utc_datetime(
                model.last_discovered_at,
            ),
            last_discovery_status=model.last_discovery_status,
            created_at=coerce_utc_datetime(model.created_at),
            updated_at=coerce_utc_datetime(model.updated_at),
        )


class SqlAlchemyToolSourceDiscoveryRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, record: ToolSourceDiscoveryRunRecord) -> None:
        self.session.add(self._to_model(record))

    def list_by_source(
        self,
        source_id: str,
        *,
        limit: int = 20,
    ) -> tuple[ToolSourceDiscoveryRunRecord, ...]:
        bounded_limit = max(1, min(int(limit), 200))
        models = self.session.scalars(
            select(ToolSourceDiscoveryRunModel)
            .where(ToolSourceDiscoveryRunModel.source_id == source_id)
            .order_by(ToolSourceDiscoveryRunModel.discovered_at.desc())
            .limit(bounded_limit),
        ).all()
        return tuple(self._to_record(model) for model in models)

    @staticmethod
    def _to_model(
        record: ToolSourceDiscoveryRunRecord,
    ) -> ToolSourceDiscoveryRunModel:
        return ToolSourceDiscoveryRunModel(
            discovery_run_id=record.discovery_run_id,
            source_id=record.source_id,
            source_revision=record.source_revision,
            config_hash=record.config_hash,
            status=record.status.value,
            discovered_at=record.discovered_at,
            function_count=record.function_count,
            provider_backend_count=record.provider_backend_count,
            error_message=record.error_message,
            metadata_payload=dict(record.metadata),
        )

    @staticmethod
    def _to_record(
        model: ToolSourceDiscoveryRunModel,
    ) -> ToolSourceDiscoveryRunRecord:
        return ToolSourceDiscoveryRunRecord(
            discovery_run_id=model.discovery_run_id,
            source_id=model.source_id,
            source_revision=model.source_revision,
            config_hash=model.config_hash,
            status=model.status,
            discovered_at=coerce_utc_datetime(model.discovered_at),
            function_count=model.function_count,
            provider_backend_count=model.provider_backend_count,
            error_message=model.error_message,
            metadata=_dict_payload(model.metadata_payload),
        )


class SqlAlchemyToolFunctionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolFunctionModel] = {}

    def upsert(self, function: ToolFunction) -> None:
        model = self._loaded_models.get(function.id)
        if model is None:
            model = self.session.get(ToolFunctionModel, function.id)
        if model is None:
            model = self._to_model(function)
            self.session.add(model)
        else:
            self._apply_to_model(model, function)
        self._loaded_models[function.id] = model

    def get(self, function_id: str) -> ToolFunction | None:
        model = self.session.get(ToolFunctionModel, function_id)
        if model is None:
            return None
        self._loaded_models[function_id] = model
        return self._to_entity(model)

    def get_by_stable_key(self, stable_key: str) -> ToolFunction | None:
        model = self.session.scalars(
            select(ToolFunctionModel)
            .where(ToolFunctionModel.stable_key == stable_key)
            .limit(1),
        ).first()
        if model is None:
            return None
        self._loaded_models[model.function_id] = model
        return self._to_entity(model)

    def list(
        self,
        *,
        source_id: str | None = None,
        status: ToolFunctionStatus | str | None = None,
    ) -> list[ToolFunction]:
        statement = select(ToolFunctionModel)
        if source_id is not None:
            statement = statement.where(ToolFunctionModel.source_id == source_id)
        status_value = _enum_filter_value(status)
        if status_value is not None:
            statement = statement.where(ToolFunctionModel.status == status_value)
        models = self.session.scalars(
            statement.order_by(ToolFunctionModel.updated_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.function_id] = model
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_model(function: ToolFunction) -> ToolFunctionModel:
        return ToolFunctionModel(
            **SqlAlchemyToolFunctionRepository._to_mapping(function),
        )

    @staticmethod
    def _to_mapping(function: ToolFunction) -> dict[str, object]:
        return {
            "function_id": function.function_id,
            "source_id": function.source_id,
            "stable_key": function.stable_key,
            "name": function.name,
            "display_name": function.display_name,
            "description": function.description,
            "input_schema_payload": dict(function.input_schema),
            "runtime_kind": function.runtime_kind.value,
            "handler_ref_payload": dict(function.handler_ref),
            "capability_ids_payload": list(function.capability_ids),
            "credential_requirements_payload": [
                dict(requirement)
                for requirement in function.credential_requirements
            ],
            "access_requirement_sets_payload": [
                list(requirement_set)
                for requirement_set in function.access_requirement_sets
            ],
            "runtime_requirements_payload": [
                dict(requirement)
                for requirement in function.runtime_requirements
            ],
            "required_effect_ids_payload": list(function.required_effect_ids),
            "execution_support_payload": _execution_support_to_payload(
                function.execution_support,
            ),
            "enabled": function.enabled,
            "trust_policy_payload": dict(function.trust_policy),
            "approval_policy_payload": dict(function.approval_policy),
            "credential_binding_overrides_payload": dict(
                function.credential_binding_overrides,
            ),
            "required_effect_overrides_payload": (
                list(function.required_effect_overrides)
                if function.required_effect_overrides is not None
                else None
            ),
            "metadata_payload": dict(function.metadata),
            "schema_hash": function.schema_hash,
            "status": function.status.value,
            "revision": function.revision,
            "created_at": function.created_at,
            "updated_at": function.updated_at,
            "last_seen_at": function.last_seen_at,
            "stale_since": function.stale_since,
            "deprecated_at": function.deprecated_at,
        }

    @staticmethod
    def _apply_to_model(
        model: ToolFunctionModel,
        function: ToolFunction,
    ) -> None:
        mapping = SqlAlchemyToolFunctionRepository._to_mapping(function)
        for key, value in mapping.items():
            setattr(model, key, value)

    @staticmethod
    def _to_entity(model: ToolFunctionModel) -> ToolFunction:
        return ToolFunction(
            id=model.function_id,
            source_id=model.source_id,
            stable_key=model.stable_key,
            name=model.name,
            display_name=model.display_name,
            description=model.description,
            input_schema=_dict_payload(model.input_schema_payload),
            runtime_kind=ToolFunctionRuntimeKind(model.runtime_kind),
            handler_ref=_dict_payload(model.handler_ref_payload),
            capability_ids=_string_tuple_payload(model.capability_ids_payload),
            credential_requirements=_dict_tuple_payload(
                model.credential_requirements_payload,
            ),
            access_requirement_sets=tuple(
                tuple(requirement_set)
                for requirement_set in model.access_requirement_sets_payload
                if isinstance(requirement_set, list | tuple)
            ),
            runtime_requirements=_dict_tuple_payload(
                model.runtime_requirements_payload,
            ),
            required_effect_ids=_string_tuple_payload(
                model.required_effect_ids_payload,
            ),
            execution_support=_execution_support_from_payload(
                model.execution_support_payload,
            ),
            enabled=model.enabled,
            trust_policy=_dict_payload(model.trust_policy_payload),
            approval_policy=_dict_payload(model.approval_policy_payload),
            credential_binding_overrides={
                str(key): str(value)
                for key, value in _dict_payload(
                    model.credential_binding_overrides_payload,
                ).items()
            },
            required_effect_overrides=(
                _string_tuple_payload(model.required_effect_overrides_payload)
                if model.required_effect_overrides_payload is not None
                else None
            ),
            metadata=_dict_payload(model.metadata_payload),
            schema_hash=model.schema_hash,
            status=ToolFunctionStatus(model.status),
            revision=model.revision,
            created_at=coerce_utc_datetime(model.created_at),
            updated_at=coerce_utc_datetime(model.updated_at),
            last_seen_at=coerce_optional_utc_datetime(model.last_seen_at),
            stale_since=coerce_optional_utc_datetime(model.stale_since),
            deprecated_at=coerce_optional_utc_datetime(model.deprecated_at),
        )


class SqlAlchemyToolFunctionCatalogRepository:
    def __init__(self, session: Session) -> None:
        self._functions = SqlAlchemyToolFunctionRepository(session)

    def list_by_source(self, source_id: str) -> tuple[ToolFunctionCatalogRecord, ...]:
        return tuple(
            _catalog_record_from_entity(function)
            for function in self._functions.list(source_id=source_id)
        )

    def add(self, function: ToolFunctionCatalogRecord) -> None:
        self._functions.upsert(_catalog_record_to_entity(function))

    def update(self, function: ToolFunctionCatalogRecord) -> None:
        self._functions.upsert(_catalog_record_to_entity(function))


def _catalog_record_to_entity(record: ToolFunctionCatalogRecord) -> ToolFunction:
    return ToolFunction(
        id=record.function_id,
        source_id=record.source_id,
        stable_key=record.stable_key,
        name=record.name,
        display_name=record.name,
        description=record.description,
        input_schema=dict(record.input_schema),
        runtime_kind=ToolFunctionRuntimeKind(record.runtime_kind.value),
        handler_ref={"ref": record.handler_ref},
        capability_ids=record.capabilities,
        credential_requirements=tuple(
            _credential_requirement_set_payload(requirement_set)
            for requirement_set in record.requirements.credential_requirements
        ),
        access_requirement_sets=record.requirements.access_requirement_sets,
        runtime_requirements=tuple(
            {"requirements": list(requirement_set)}
            for requirement_set in record.requirements.runtime_requirement_sets
        ),
        required_effect_ids=record.requirements.required_effect_ids,
        enabled=record.enabled,
        trust_policy=dict(record.trust_policy),
        approval_policy=dict(record.approval_policy),
        credential_binding_overrides=dict(record.credential_binding_overrides),
        required_effect_overrides=record.required_effect_overrides,
        metadata=dict(record.metadata),
        schema_hash=record.schema_hash,
        status=ToolFunctionStatus(record.status.value),
        revision=record.revision,
        created_at=_record_datetime(record.created_at, record.updated_at, record.last_seen_at),
        updated_at=_record_datetime(record.updated_at, record.created_at, record.last_seen_at),
        last_seen_at=record.last_seen_at,
        stale_since=record.stale_since,
        deprecated_at=record.deprecated_at,
    )


def _catalog_record_from_entity(function: ToolFunction) -> ToolFunctionCatalogRecord:
    return ToolFunctionCatalogRecord(
        function_id=function.function_id,
        source_id=function.source_id,
        stable_key=function.stable_key,
        name=function.name,
        description=function.description,
        input_schema=function.input_schema,
        runtime_kind=function.runtime_kind.value,
        handler_ref=_handler_ref_from_payload(function.handler_ref),
        requirements=ToolFunctionRequirements(
            credential_requirements=_credential_requirement_sets_from_payload(
                list(function.credential_requirements),
            ),
            access_requirement_sets=function.access_requirement_sets,
            runtime_requirement_sets=_runtime_requirement_sets_from_payload(
                function.runtime_requirements,
            ),
            required_effect_ids=function.required_effect_ids,
        ),
        capabilities=function.capability_ids,
        schema_hash=function.schema_hash,
        status=function.status.value,
        revision=function.revision,
        enabled=function.enabled,
        trust_policy=function.trust_policy,
        approval_policy=function.approval_policy,
        credential_binding_overrides=function.credential_binding_overrides,
        required_effect_overrides=function.required_effect_overrides,
        metadata=function.metadata,
        created_at=function.created_at,
        updated_at=function.updated_at,
        last_seen_at=function.last_seen_at,
        stale_since=function.stale_since,
        deprecated_at=function.deprecated_at,
    )


def _handler_ref_from_payload(payload: dict[str, Any]) -> str:
    for key in ("ref", "handler", "runtime_key"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _record_datetime(*values: datetime | None) -> datetime:
    for value in values:
        if value is not None:
            return value
    return datetime.now(timezone.utc)


def _runtime_requirement_sets_from_payload(
    payload: tuple[dict[str, Any], ...],
) -> tuple[tuple[str, ...], ...]:
    requirement_sets: list[tuple[str, ...]] = []
    for item in payload:
        raw_requirements = item.get("requirements")
        if not isinstance(raw_requirements, list | tuple):
            continue
        normalized = tuple(
            dict.fromkeys(
                str(requirement).strip()
                for requirement in raw_requirements
                if str(requirement).strip()
            ),
        )
        if normalized:
            requirement_sets.append(normalized)
    return tuple(requirement_sets)


class SqlAlchemyToolProviderBackendRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolProviderBackendModel] = {}

    def upsert(self, backend: ToolProviderBackend) -> None:
        model = self._loaded_models.get(backend.id)
        if model is None:
            model = self.session.get(ToolProviderBackendModel, backend.id)
        if model is None:
            model = self._to_model(backend)
            self.session.add(model)
        else:
            self._apply_to_model(model, backend)
        self._loaded_models[backend.id] = model

    def get(self, backend_id: str) -> ToolProviderBackend | None:
        model = self.session.get(ToolProviderBackendModel, backend_id)
        if model is None:
            return None
        self._loaded_models[backend_id] = model
        return self._to_entity(model)

    def list(
        self,
        *,
        source_id: str | None = None,
        capability: ToolProviderCapability | str | None = None,
        status: ToolProviderBackendStatus | str | None = None,
    ) -> list[ToolProviderBackend]:
        statement = select(ToolProviderBackendModel)
        if source_id is not None:
            statement = statement.where(ToolProviderBackendModel.source_id == source_id)
        capability_value = _enum_filter_value(capability)
        if capability_value is not None:
            statement = statement.where(
                ToolProviderBackendModel.capability == capability_value,
            )
        status_value = _enum_filter_value(status)
        if status_value is not None:
            statement = statement.where(ToolProviderBackendModel.status == status_value)
        models = self.session.scalars(
            statement.order_by(
                ToolProviderBackendModel.priority.asc(),
                ToolProviderBackendModel.updated_at.desc(),
            ),
        ).all()
        for model in models:
            self._loaded_models[model.backend_id] = model
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_model(backend: ToolProviderBackend) -> ToolProviderBackendModel:
        return ToolProviderBackendModel(
            **SqlAlchemyToolProviderBackendRepository._to_mapping(backend),
        )

    @staticmethod
    def _to_mapping(backend: ToolProviderBackend) -> dict[str, object]:
        return {
            "backend_id": backend.backend_id,
            "source_id": backend.source_id,
            "capability": backend.capability.value,
            "display_name": backend.display_name,
            "credential_requirements_payload": [
                dict(requirement)
                for requirement in backend.credential_requirements
            ],
            "runtime_ref_payload": dict(backend.runtime_ref),
            "priority": backend.priority,
            "enabled": backend.enabled,
            "status": backend.status.value,
            "created_at": backend.created_at,
            "updated_at": backend.updated_at,
        }

    @staticmethod
    def _apply_to_model(
        model: ToolProviderBackendModel,
        backend: ToolProviderBackend,
    ) -> None:
        mapping = SqlAlchemyToolProviderBackendRepository._to_mapping(backend)
        for key, value in mapping.items():
            setattr(model, key, value)

    @staticmethod
    def _to_entity(model: ToolProviderBackendModel) -> ToolProviderBackend:
        return ToolProviderBackend(
            id=model.backend_id,
            source_id=model.source_id,
            capability=ToolProviderCapability(model.capability),
            display_name=model.display_name,
            credential_requirements=_dict_tuple_payload(
                model.credential_requirements_payload,
            ),
            runtime_ref=_dict_payload(model.runtime_ref_payload),
            priority=model.priority,
            enabled=model.enabled,
            status=ToolProviderBackendStatus(model.status),
            created_at=coerce_utc_datetime(model.created_at),
            updated_at=coerce_utc_datetime(model.updated_at),
        )


class SqlAlchemyToolRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolRunModel] = {}

    def add(self, tool_run: ToolRun) -> None:
        model = self._loaded_models.get(tool_run.id)
        if model is None:
            model = self.session.get(ToolRunModel, tool_run.id)
        if model is None:
            self.add_new(tool_run)
            return
        self._apply_to_model(model, tool_run)
        self._loaded_models[tool_run.id] = model

    def add_new(self, tool_run: ToolRun) -> None:
        model = self._to_model(tool_run)
        self.session.add(model)
        self._loaded_models[tool_run.id] = model

    def add_many_new(self, tool_runs: tuple[ToolRun, ...]) -> None:
        if not tool_runs:
            return
        if len(tool_runs) == 1:
            self.add_new(tool_runs[0])
            return
        self.session.bulk_insert_mappings(
            ToolRunModel,
            [self._to_mapping(tool_run) for tool_run in tool_runs],
        )

    def get(self, run_id: str) -> ToolRun | None:
        model = self.session.get(ToolRunModel, run_id)
        if model is None:
            return None
        self._loaded_models[run_id] = model
        return self._to_entity(model)

    def get_many(self, run_ids: tuple[str, ...]) -> dict[str, ToolRun]:
        if not run_ids:
            return {}
        ordered_ids = tuple(dict.fromkeys(run_ids))
        models = self.session.scalars(
            select(ToolRunModel).where(ToolRunModel.id.in_(ordered_ids)),
        ).all()
        entities: dict[str, ToolRun] = {}
        for model in models:
            self._loaded_models[model.id] = model
            entities[model.id] = self._to_entity(model)
        return entities

    def list(self) -> list[ToolRun]:
        models = self.session.scalars(
            select(ToolRunModel).order_by(ToolRunModel.created_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    def list_for_tool(self, tool_id: str) -> list[ToolRun]:
        models = self.session.scalars(
            select(ToolRunModel)
            .where(ToolRunModel.tool_id == tool_id)
            .order_by(ToolRunModel.created_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_model(tool_run: ToolRun) -> ToolRunModel:
        return ToolRunModel(
            **SqlAlchemyToolRunRepository._to_mapping(tool_run),
        )

    @staticmethod
    def _to_mapping(tool_run: ToolRun) -> dict[str, object]:
        return {
            "id": tool_run.id,
            "tool_id": tool_run.tool_id,
            "function_id": tool_run.function_id,
            "function_revision": tool_run.function_revision,
            "source_id": tool_run.source_id,
            "source_revision": tool_run.source_revision,
            "schema_hash": tool_run.schema_hash,
            "mode": tool_run.target.mode.value,
            "strategy": tool_run.target.strategy.value,
            "environment": tool_run.target.environment.value,
            "status": tool_run.status.value,
            "input_payload": tool_run.input_payload,
            "metadata_payload": tool_run.metadata,
            "invocation_context_payload": tool_run.invocation_context_payload,
            "output_payload": tool_run.stored_output_payload,
            "error_message": tool_run.stored_error_payload,
            "created_at": tool_run.created_at,
            "started_at": tool_run.started_at,
            "completed_at": tool_run.completed_at,
            "attempt_count": tool_run.attempt_count,
            "max_attempts": tool_run.max_attempts,
            "worker_id": tool_run.worker_id,
            "heartbeat_at": tool_run.heartbeat_at,
            "lease_expires_at": tool_run.lease_expires_at,
            "cancel_requested_at": tool_run.cancel_requested_at,
        }

    @staticmethod
    def _apply_to_model(model: ToolRunModel, tool_run: ToolRun) -> None:
        model.tool_id = tool_run.tool_id
        model.function_id = tool_run.function_id
        model.function_revision = tool_run.function_revision
        model.source_id = tool_run.source_id
        model.source_revision = tool_run.source_revision
        model.schema_hash = tool_run.schema_hash
        model.mode = tool_run.target.mode.value
        model.strategy = tool_run.target.strategy.value
        model.environment = tool_run.target.environment.value
        model.status = tool_run.status.value
        model.input_payload = tool_run.input_payload
        model.metadata_payload = tool_run.metadata
        model.invocation_context_payload = tool_run.invocation_context_payload
        model.output_payload = tool_run.stored_output_payload
        model.error_message = tool_run.stored_error_payload
        model.created_at = tool_run.created_at
        model.started_at = tool_run.started_at
        model.completed_at = tool_run.completed_at
        model.attempt_count = tool_run.attempt_count
        model.max_attempts = tool_run.max_attempts
        model.worker_id = tool_run.worker_id
        model.heartbeat_at = tool_run.heartbeat_at
        model.lease_expires_at = tool_run.lease_expires_at
        model.cancel_requested_at = tool_run.cancel_requested_at

    @staticmethod
    def _to_entity(model: ToolRunModel) -> ToolRun:
        return ToolRun(
            id=model.id,
            tool_id=model.tool_id,
            function_id=model.function_id,
            function_revision=model.function_revision,
            source_id=model.source_id,
            source_revision=model.source_revision,
            schema_hash=model.schema_hash,
            target=ToolExecutionTarget(
                mode=ToolMode(model.mode),
                strategy=ToolExecutionStrategy(model.strategy),
                environment=ToolEnvironment(model.environment),
            ),
            status=ToolRunStatus(model.status),
            input_payload=dict(model.input_payload),
            metadata=dict(model.metadata_payload or {}),
            invocation_context_payload=(
                dict(model.invocation_context_payload)
                if model.invocation_context_payload is not None
                else None
            ),
            result_payload=model.output_payload,
            error_payload=model.error_message,
            created_at=coerce_utc_datetime(model.created_at),
            started_at=coerce_optional_utc_datetime(model.started_at),
            completed_at=coerce_optional_utc_datetime(model.completed_at),
            attempt_count=model.attempt_count,
            max_attempts=model.max_attempts,
            worker_id=model.worker_id,
            heartbeat_at=coerce_optional_utc_datetime(model.heartbeat_at),
            lease_expires_at=coerce_optional_utc_datetime(model.lease_expires_at),
            cancel_requested_at=coerce_optional_utc_datetime(
                model.cancel_requested_at,
            ),
        )


class SqlAlchemyToolRunAssignmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolRunAssignmentModel] = {}

    def add(self, assignment: ToolRunAssignment) -> None:
        model = self._loaded_models.get(assignment.id)
        if model is None:
            model = self.session.get(ToolRunAssignmentModel, assignment.id)
        if model is None:
            self.add_new(assignment)
            return
        self._apply_to_model(model, assignment)
        self._loaded_models[assignment.id] = model

    def add_new(self, assignment: ToolRunAssignment) -> None:
        model = self._to_model(assignment)
        self.session.add(model)
        self._loaded_models[assignment.id] = model

    def get(self, assignment_id: str) -> ToolRunAssignment | None:
        model = self.session.get(ToolRunAssignmentModel, assignment_id)
        if model is None:
            return None
        self._loaded_models[assignment_id] = model
        return self._to_entity(model)

    def get_latest_for_run(self, run_id: str) -> ToolRunAssignment | None:
        model = self.session.scalars(
            select(ToolRunAssignmentModel)
            .where(ToolRunAssignmentModel.run_id == run_id)
            .order_by(ToolRunAssignmentModel.assigned_at.desc())
            .limit(1),
        ).first()
        if model is None:
            return None
        self._loaded_models[model.id] = model
        return self._to_entity(model)

    def get_latest_for_run_and_worker(
        self,
        run_id: str,
        worker_id: str,
    ) -> ToolRunAssignment | None:
        model = self.session.scalars(
            select(ToolRunAssignmentModel)
            .where(
                ToolRunAssignmentModel.run_id == run_id,
                ToolRunAssignmentModel.worker_id == worker_id,
            )
            .order_by(ToolRunAssignmentModel.assigned_at.desc())
            .limit(1),
        ).first()
        if model is None:
            return None
        self._loaded_models[model.id] = model
        return self._to_entity(model)

    def list_for_run(self, run_id: str) -> list[ToolRunAssignment]:
        models = self.session.scalars(
            select(ToolRunAssignmentModel)
            .where(ToolRunAssignmentModel.run_id == run_id)
            .order_by(ToolRunAssignmentModel.assigned_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    def get_next_for_worker(self, worker_id: str) -> ToolRunAssignment | None:
        model = self.session.scalars(
            select(ToolRunAssignmentModel)
            .where(
                ToolRunAssignmentModel.worker_id == worker_id,
                ToolRunAssignmentModel.status.in_(
                    (
                        ToolRunAssignmentStatus.ASSIGNED.value,
                        ToolRunAssignmentStatus.RUNNING.value,
                    ),
                ),
            )
            .order_by(ToolRunAssignmentModel.assigned_at.asc())
            .limit(1),
        ).first()
        if model is None:
            return None
        self._loaded_models[model.id] = model
        return self._to_entity(model)

    def list_for_worker(self, worker_id: str) -> list[ToolRunAssignment]:
        models = self.session.scalars(
            select(ToolRunAssignmentModel)
            .where(ToolRunAssignmentModel.worker_id == worker_id)
            .order_by(ToolRunAssignmentModel.assigned_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    def list(self) -> list[ToolRunAssignment]:
        models = self.session.scalars(
            select(ToolRunAssignmentModel).order_by(
                ToolRunAssignmentModel.assigned_at.desc(),
            ),
        ).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_model(assignment: ToolRunAssignment) -> ToolRunAssignmentModel:
        return ToolRunAssignmentModel(
            **SqlAlchemyToolRunAssignmentRepository._to_mapping(assignment),
        )

    @staticmethod
    def _to_mapping(assignment: ToolRunAssignment) -> dict[str, object]:
        return {
            "id": assignment.id,
            "run_id": assignment.run_id,
            "tool_id": assignment.tool_id,
            "worker_id": assignment.worker_id,
            "status": assignment.status.value,
            "attempt_count": assignment.attempt_count,
            "assigned_at": assignment.assigned_at,
            "started_at": assignment.started_at,
            "heartbeat_at": assignment.heartbeat_at,
            "lease_expires_at": assignment.lease_expires_at,
            "completed_at": assignment.completed_at,
            "terminal_reason": assignment.terminal_reason,
        }

    @staticmethod
    def _apply_to_model(
        model: ToolRunAssignmentModel,
        assignment: ToolRunAssignment,
    ) -> None:
        model.run_id = assignment.run_id
        model.tool_id = assignment.tool_id
        model.worker_id = assignment.worker_id
        model.status = assignment.status.value
        model.attempt_count = assignment.attempt_count
        model.assigned_at = assignment.assigned_at
        model.started_at = assignment.started_at
        model.heartbeat_at = assignment.heartbeat_at
        model.lease_expires_at = assignment.lease_expires_at
        model.completed_at = assignment.completed_at
        model.terminal_reason = assignment.terminal_reason

    @staticmethod
    def _to_entity(model: ToolRunAssignmentModel) -> ToolRunAssignment:
        return ToolRunAssignment(
            id=model.id,
            run_id=model.run_id,
            tool_id=model.tool_id,
            worker_id=model.worker_id,
            status=ToolRunAssignmentStatus(model.status),
            attempt_count=model.attempt_count,
            assigned_at=coerce_utc_datetime(model.assigned_at),
            started_at=coerce_optional_utc_datetime(model.started_at),
            heartbeat_at=coerce_optional_utc_datetime(model.heartbeat_at),
            lease_expires_at=coerce_optional_utc_datetime(model.lease_expires_at),
            completed_at=coerce_optional_utc_datetime(model.completed_at),
            terminal_reason=model.terminal_reason,
        )


class SqlAlchemyToolWorkerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolWorkerModel] = {}

    def add(self, worker: ToolWorkerRegistration) -> None:
        model = self._loaded_models.get(worker.id)
        if model is None:
            model = self.session.get(ToolWorkerModel, worker.id)
        if model is None:
            self.add_new(worker)
            return
        self._apply_to_model(model, worker)
        self._loaded_models[worker.id] = model

    def add_new(self, worker: ToolWorkerRegistration) -> None:
        model = self._to_model(worker)
        self.session.add(model)
        self._loaded_models[worker.id] = model

    def get(self, worker_id: str) -> ToolWorkerRegistration | None:
        model = self.session.get(ToolWorkerModel, worker_id)
        if model is None:
            return None
        self._loaded_models[worker_id] = model
        return self._to_entity(model)

    def list(self) -> list[ToolWorkerRegistration]:
        models = self.session.scalars(
            select(ToolWorkerModel).order_by(ToolWorkerModel.registered_at.asc()),
        ).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    def delete(self, worker_id: str) -> None:
        model = self._loaded_models.pop(worker_id, None)
        if model is None:
            model = self.session.get(ToolWorkerModel, worker_id)
        if model is not None:
            self.session.delete(model)

    @staticmethod
    def _to_model(worker: ToolWorkerRegistration) -> ToolWorkerModel:
        return ToolWorkerModel(
            **SqlAlchemyToolWorkerRepository._to_mapping(worker),
        )

    @staticmethod
    def _to_mapping(worker: ToolWorkerRegistration) -> dict[str, object]:
        return {
            "id": worker.id,
            "status": worker.status.value,
            "max_in_flight": worker.max_in_flight,
            "current_in_flight": worker.current_in_flight,
            "capabilities_payload": dict(worker.capabilities_payload),
            "registered_at": worker.registered_at,
            "heartbeat_at": worker.heartbeat_at,
            "lease_expires_at": worker.lease_expires_at,
        }

    @staticmethod
    def _apply_to_model(model: ToolWorkerModel, worker: ToolWorkerRegistration) -> None:
        model.status = worker.status.value
        model.max_in_flight = worker.max_in_flight
        model.current_in_flight = worker.current_in_flight
        model.capabilities_payload = dict(worker.capabilities_payload)
        model.registered_at = worker.registered_at
        model.heartbeat_at = worker.heartbeat_at
        model.lease_expires_at = worker.lease_expires_at

    @staticmethod
    def _to_entity(model: ToolWorkerModel) -> ToolWorkerRegistration:
        return ToolWorkerRegistration(
            id=model.id,
            status=ToolWorkerStatus(model.status),
            max_in_flight=model.max_in_flight,
            current_in_flight=model.current_in_flight,
            capabilities_payload=dict(model.capabilities_payload),
            registered_at=coerce_utc_datetime(model.registered_at),
            heartbeat_at=coerce_utc_datetime(model.heartbeat_at),
            lease_expires_at=coerce_optional_utc_datetime(model.lease_expires_at),
        )
