from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal

from crxzipple.modules.events.domain import EventKind


EventContractDurability = Literal["persistent", "transient"]
_ALLOWED_EVENT_KINDS = {"command", "fact", "broadcast", "observe", "live"}


def _normalize_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _normalize_text_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(item.strip() for item in values if isinstance(item, str) and item.strip())


def _normalize_version(value: int) -> int:
    if not isinstance(value, int) or value < 1:
        raise ValueError("event contract version must be a positive integer.")
    return value


@dataclass(frozen=True, slots=True)
class EventTopicContract:
    contract_id: str
    topic_pattern: str
    owner: str
    description: str
    kinds: tuple[EventKind, ...] = ("fact",)
    producers: tuple[str, ...] = field(default_factory=tuple)
    consumers: tuple[str, ...] = field(default_factory=tuple)
    durability: EventContractDurability = "persistent"
    ordering: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)
    version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "contract_id",
            _normalize_text(self.contract_id, field_name="contract_id"),
        )
        object.__setattr__(
            self,
            "topic_pattern",
            _normalize_text(self.topic_pattern, field_name="topic_pattern"),
        )
        object.__setattr__(self, "owner", _normalize_text(self.owner, field_name="owner"))
        object.__setattr__(
            self,
            "description",
            _normalize_text(self.description, field_name="description"),
        )
        object.__setattr__(
            self,
            "kinds",
            tuple(kind for kind in self.kinds if kind in _ALLOWED_EVENT_KINDS),
        )
        object.__setattr__(self, "producers", _normalize_text_tuple(self.producers))
        object.__setattr__(self, "consumers", _normalize_text_tuple(self.consumers))
        object.__setattr__(self, "notes", _normalize_text_tuple(self.notes))
        object.__setattr__(self, "version", _normalize_version(self.version))

    def to_payload(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "version": self.version,
            "topic_pattern": self.topic_pattern,
            "owner": self.owner,
            "description": self.description,
            "kinds": list(self.kinds),
            "producers": list(self.producers),
            "consumers": list(self.consumers),
            "durability": self.durability,
            "ordering": self.ordering,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class EventRouteContract:
    contract_id: str
    source_topic_pattern: str
    target_topic_pattern: str
    owner: str
    description: str
    observer: str
    subscription_id_pattern: str | None = None
    source_kinds: tuple[EventKind, ...] = field(default_factory=tuple)
    target_kind: EventKind | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)
    version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "contract_id",
            _normalize_text(self.contract_id, field_name="contract_id"),
        )
        object.__setattr__(
            self,
            "source_topic_pattern",
            _normalize_text(
                self.source_topic_pattern,
                field_name="source_topic_pattern",
            ),
        )
        object.__setattr__(
            self,
            "target_topic_pattern",
            _normalize_text(
                self.target_topic_pattern,
                field_name="target_topic_pattern",
            ),
        )
        object.__setattr__(self, "owner", _normalize_text(self.owner, field_name="owner"))
        object.__setattr__(
            self,
            "description",
            _normalize_text(self.description, field_name="description"),
        )
        object.__setattr__(
            self,
            "observer",
            _normalize_text(self.observer, field_name="observer"),
        )
        object.__setattr__(
            self,
            "source_kinds",
            tuple(
                kind
                for kind in self.source_kinds
                if kind in _ALLOWED_EVENT_KINDS
            ),
        )
        object.__setattr__(self, "notes", _normalize_text_tuple(self.notes))
        object.__setattr__(self, "version", _normalize_version(self.version))

    def to_payload(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "version": self.version,
            "source_topic_pattern": self.source_topic_pattern,
            "target_topic_pattern": self.target_topic_pattern,
            "owner": self.owner,
            "description": self.description,
            "observer": self.observer,
            "subscription_id_pattern": self.subscription_id_pattern,
            "source_kinds": list(self.source_kinds),
            "target_kind": self.target_kind,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class EventTopicContractMatch:
    contract: EventTopicContract
    variables: dict[str, str] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "contract": self.contract.to_payload(),
            "variables": dict(self.variables),
        }


@dataclass(frozen=True, slots=True)
class EventRouteContractMatch:
    contract: EventRouteContract
    direction: Literal["source", "target"]
    variables: dict[str, str] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "contract": self.contract.to_payload(),
            "direction": self.direction,
            "variables": dict(self.variables),
        }


class EventContractRegistry:
    def __init__(
        self,
        *,
        topic_contracts: tuple[EventTopicContract, ...] = (),
        route_contracts: tuple[EventRouteContract, ...] = (),
    ) -> None:
        self._topic_contracts: dict[str, EventTopicContract] = {}
        self._route_contracts: dict[str, EventRouteContract] = {}
        for contract in topic_contracts:
            self.register_topic(contract)
        for contract in route_contracts:
            self.register_route(contract)

    def register_topic(self, contract: EventTopicContract) -> None:
        if contract.contract_id in self._topic_contracts:
            raise ValueError(
                f"event topic contract '{contract.contract_id}' is already registered.",
            )
        self._topic_contracts[contract.contract_id] = contract

    def register_route(self, contract: EventRouteContract) -> None:
        if contract.contract_id in self._route_contracts:
            raise ValueError(
                f"event route contract '{contract.contract_id}' is already registered.",
            )
        self._route_contracts[contract.contract_id] = contract

    def register_topics(self, contracts: tuple[EventTopicContract, ...]) -> None:
        for contract in contracts:
            self.register_topic(contract)

    def register_routes(self, contracts: tuple[EventRouteContract, ...]) -> None:
        for contract in contracts:
            self.register_route(contract)

    def list_topic_contracts(self) -> tuple[EventTopicContract, ...]:
        return tuple(
            self._topic_contracts[key]
            for key in sorted(self._topic_contracts)
        )

    def list_route_contracts(self) -> tuple[EventRouteContract, ...]:
        return tuple(
            self._route_contracts[key]
            for key in sorted(self._route_contracts)
        )

    def get_topic_contract(self, contract_id: str) -> EventTopicContract | None:
        return self._topic_contracts.get(contract_id.strip())

    def get_route_contract(self, contract_id: str) -> EventRouteContract | None:
        return self._route_contracts.get(contract_id.strip())

    def match_topic_contracts(self, topic: str) -> tuple[EventTopicContractMatch, ...]:
        return tuple(
            EventTopicContractMatch(contract=contract, variables=variables)
            for contract in self.list_topic_contracts()
            if (variables := _match_topic_pattern(contract.topic_pattern, topic)) is not None
        )

    def match_route_contracts(
        self,
        topic: str,
        *,
        direction: Literal["source", "target"] | None = None,
    ) -> tuple[EventRouteContractMatch, ...]:
        matches: list[EventRouteContractMatch] = []
        for contract in self.list_route_contracts():
            if direction in {None, "source"}:
                source_variables = _match_topic_pattern(
                    contract.source_topic_pattern,
                    topic,
                )
                if source_variables is not None:
                    matches.append(
                        EventRouteContractMatch(
                            contract=contract,
                            direction="source",
                            variables=source_variables,
                        ),
                    )
            if direction in {None, "target"}:
                target_variables = _match_topic_pattern(
                    contract.target_topic_pattern,
                    topic,
                )
                if target_variables is not None:
                    matches.append(
                        EventRouteContractMatch(
                            contract=contract,
                            direction="target",
                            variables=target_variables,
                        ),
                    )
        return tuple(matches)

    def to_payload(self) -> dict[str, Any]:
        topics = [contract.to_payload() for contract in self.list_topic_contracts()]
        routes = [contract.to_payload() for contract in self.list_route_contracts()]
        return {
            "topic_count": len(topics),
            "route_count": len(routes),
            "topics": topics,
            "routes": routes,
        }


def _match_topic_pattern(pattern: str, topic: str) -> dict[str, str] | None:
    names: list[str] = []
    parts: list[str] = []
    cursor = 0
    for match in re.finditer(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", pattern):
        parts.append(re.escape(pattern[cursor:match.start()]))
        name = match.group(1)
        names.append(name)
        parts.append(f"(?P<{name}>[^.]+)")
        cursor = match.end()
    parts.append(re.escape(pattern[cursor:]))
    expression = "^" + "".join(parts) + "$"
    matched = re.match(expression, topic)
    if matched is None:
        return None
    return {name: matched.group(name) for name in names}
