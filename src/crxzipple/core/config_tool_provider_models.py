from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpenApiCredentialBinding:
    scheme_name: str
    credential_binding_id: str | None = None
    username_binding_id: str | None = None
    password_binding_id: str | None = None


@dataclass(frozen=True, slots=True)
class OpenApiProviderSettings:
    name: str
    spec_location: str
    base_url: str | None = None
    description: str = ""
    timeout_seconds: int = 30
    max_concurrency: int | None = None
    credential_bindings: tuple[OpenApiCredentialBinding, ...] = ()
    default_effect_ids: tuple[str, ...] = ()
    runtime_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "runtime_requirements",
            tuple(
                dict.fromkeys(
                    str(requirement).strip()
                    for requirement in self.runtime_requirements
                    if str(requirement).strip()
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class McpProviderSettings:
    name: str
    command: tuple[str, ...] = ()
    transport: str = "stdio"
    endpoint_url: str | None = None
    description: str = ""
    timeout_seconds: int = 30
    max_concurrency: int | None = None
    default_effect_ids: tuple[str, ...] = ()
    runtime_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        transport = self.transport.strip().lower()
        if transport not in {"stdio", "http"}:
            raise ValueError(
                f"MCP provider '{self.name}' transport must be one of: http, stdio.",
            )
        command = tuple(part.strip() for part in self.command if part.strip())
        endpoint_url = (
            self.endpoint_url.strip() if isinstance(self.endpoint_url, str) else ""
        )
        if transport == "stdio" and not command:
            raise ValueError(f"MCP provider '{self.name}' command cannot be empty.")
        if transport == "http" and not endpoint_url:
            raise ValueError(f"MCP provider '{self.name}' endpoint_url cannot be empty.")
        object.__setattr__(self, "transport", transport)
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "endpoint_url", endpoint_url or None)
        object.__setattr__(
            self,
            "runtime_requirements",
            tuple(
                dict.fromkeys(
                    str(requirement).strip()
                    for requirement in self.runtime_requirements
                    if str(requirement).strip()
                ),
            ),
        )
