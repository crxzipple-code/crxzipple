from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping


class AccessReadinessStatus(StrEnum):
    READY = "ready"
    SETUP_NEEDED = "setup_needed"
    WAITING_USER = "waiting_user"
    EXPIRED = "expired"
    CREDENTIAL_KIND_MISMATCH = "credential_kind_mismatch"
    CREDENTIAL_SOURCE_KIND_MISMATCH = "credential_source_kind_mismatch"
    UNSUPPORTED = "unsupported"


class AccessSetupFlowKind(StrEnum):
    ENV = "env"
    FILE = "file"
    COMMAND = "command"
    OAUTH_BROWSER = "oauth_browser"
    DEVICE_CODE = "device_code"
    MESSAGE = "message"
    UNSUPPORTED = "unsupported"


class AccessSetupActionKind(StrEnum):
    CONFIGURE_ENV = "configure_env"
    CREATE_FILE = "create_file"
    RUN_COMMAND = "run_command"
    OPEN_URL = "open_url"
    SHOW_MESSAGE = "show_message"


@dataclass(frozen=True, slots=True)
class AccessRequirement:
    raw: str
    provider: str | None = None
    kind: str | None = None
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AccessSetupAction:
    kind: AccessSetupActionKind
    label: str
    description: str | None = None
    command: tuple[str, ...] = ()
    url: str | None = None
    path: str | None = None
    env_vars: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": self.kind.value,
            "label": self.label,
        }
        if self.description:
            payload["description"] = self.description
        if self.command:
            payload["command"] = list(self.command)
        if self.url:
            payload["url"] = self.url
        if self.path:
            payload["path"] = self.path
        if self.env_vars:
            payload["env_vars"] = list(self.env_vars)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True, slots=True)
class AccessSetupFlow:
    kind: AccessSetupFlowKind
    title: str
    description: str
    action_label: str | None = None
    env_vars: tuple[str, ...] = ()
    path: str | None = None
    command: tuple[str, ...] = ()
    authorize_url: str | None = None
    callback_url: str | None = None
    verification_url: str | None = None
    user_code: str | None = None
    expires_at: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    actions: tuple[AccessSetupAction, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": self.kind.value,
            "title": self.title,
            "description": self.description,
        }
        if self.action_label:
            payload["action_label"] = self.action_label
        if self.env_vars:
            payload["env_vars"] = list(self.env_vars)
        if self.path:
            payload["path"] = self.path
        if self.command:
            payload["command"] = list(self.command)
        if self.authorize_url:
            payload["authorize_url"] = self.authorize_url
        if self.callback_url:
            payload["callback_url"] = self.callback_url
        if self.verification_url:
            payload["verification_url"] = self.verification_url
        if self.user_code:
            payload["user_code"] = self.user_code
        if self.expires_at:
            payload["expires_at"] = self.expires_at
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        if self.actions:
            payload["actions"] = [action.to_payload() for action in self.actions]
        return payload


@dataclass(frozen=True, slots=True)
class AccessRequirementReadiness:
    requirement: AccessRequirement
    status: AccessReadinessStatus
    reason: str
    setup_flow: AccessSetupFlow | None = None

    @property
    def ready(self) -> bool:
        return self.status is AccessReadinessStatus.READY

    @property
    def setup_available(self) -> bool:
        if self.setup_flow is None:
            return False
        return self.setup_flow.kind is not AccessSetupFlowKind.UNSUPPORTED

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "requirement": self.requirement.raw,
            "provider": self.requirement.provider,
            "kind": self.requirement.kind,
            "scopes": list(self.requirement.scopes),
            "status": self.status.value,
            "ready": self.ready,
            "setup_available": self.setup_available,
            "reason": self.reason,
        }
        if self.setup_flow is not None:
            payload["setup_flow"] = self.setup_flow.to_payload()
        return payload
