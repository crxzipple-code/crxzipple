from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.shared.domain import ValueObject


_DEFAULT_CAPABILITY_DESCRIPTIONS: tuple[tuple[str, str, str], ...] = (
    ("credential.read", "Credential Read", "Read resolved credential metadata."),
    ("access.readiness", "Access Readiness", "Check external access readiness."),
    ("artifact.read", "Artifact Read", "Read artifact metadata or content."),
    ("artifact.write", "Artifact Write", "Write artifact metadata or content."),
    ("bounded_network.http", "Bounded HTTP Network", "Perform bounded HTTP calls."),
    ("workspace.lookup", "Workspace Lookup", "Resolve workspace paths and metadata."),
    ("workspace.read", "Workspace Read", "Read files under a workspace boundary."),
    ("workspace.write", "Workspace Write", "Write files under a workspace boundary."),
    ("process.spawn", "Process Spawn", "Start a local process."),
    ("process.manage", "Process Manage", "Inspect or control a local process."),
    ("browser.profile_read", "Browser Profile Read", "Read browser profile metadata."),
    ("browser.control", "Browser Control", "Control browser runtime lifecycle."),
    ("browser.page_action", "Browser Page Action", "Act on a browser page."),
    (
        "browser.artifact_write",
        "Browser Artifact Write",
        "Persist browser-produced artifacts.",
    ),
    (
        "browser.runtime_readiness",
        "Browser Runtime Readiness",
        "Check browser runtime readiness.",
    ),
    (
        "runtime_settings.read",
        "Runtime Settings Read",
        "Read effective runtime settings.",
    ),
    ("mobile.device_read", "Mobile Device Read", "Read mobile device metadata."),
    ("mobile.action", "Mobile Action", "Act on a mobile device."),
    ("mobile.screenshot", "Mobile Screenshot", "Capture a mobile screenshot."),
    (
        "memory.context_lookup",
        "Memory Context Lookup",
        "Resolve memory context candidates.",
    ),
    ("memory.search", "Memory Search", "Search memory indexes."),
    ("memory.read", "Memory Read", "Read memory content."),
    ("memory.write", "Memory Write", "Write memory content."),
    ("memory.flush_marker", "Memory Flush Marker", "Write a memory flush marker."),
    ("session.read", "Session Read", "Read session state or messages."),
    ("session.write", "Session Write", "Write session state or messages."),
    ("session.tree_read", "Session Tree Read", "Read a session tree."),
    (
        "session.route_enqueue",
        "Session Route Enqueue",
        "Enqueue session routing work.",
    ),
    ("session.tree_cancel", "Session Tree Cancel", "Cancel a session tree branch."),
    ("run_control.yield", "Run Control Yield", "Yield execution back to the caller."),
    ("tool_catalog.read", "Tool Catalog Read", "Read the tool catalog."),
    ("skill.read", "Skill Read", "Read skill package content or metadata."),
    (
        "skill.authoring",
        "Skill Authoring",
        "Create, validate, diff, apply, or reject governed skill drafts.",
    ),
)


def _normalize_capability_id(value: str) -> str:
    capability_id = value.strip()
    if not capability_id:
        raise ToolValidationError("Tool capability id cannot be empty.")
    if capability_id.startswith("orchestration."):
        raise ToolValidationError(
            f"Tool capability '{capability_id}' is not a formal capability.",
        )
    return capability_id


def _normalize_capability_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_normalize_capability_id(value) for value in values))


@dataclass(frozen=True, slots=True)
class ToolCapabilityRequirement(ValueObject):
    id: str
    label: str
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _normalize_capability_id(self.id))
        if not self.label.strip():
            raise ToolValidationError("Tool capability label cannot be empty.")
        if not self.description.strip():
            raise ToolValidationError("Tool capability description cannot be empty.")
        object.__setattr__(self, "label", self.label.strip())
        object.__setattr__(self, "description", self.description.strip())


@dataclass(frozen=True, slots=True)
class ToolPackageCapabilityManifest(ValueObject):
    package_id: str
    capability_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        package_id = self.package_id.strip()
        if not package_id:
            raise ToolValidationError(
                "Tool capability manifest package_id cannot be empty.",
            )
        object.__setattr__(self, "package_id", package_id)
        object.__setattr__(
            self,
            "capability_ids",
            _normalize_capability_ids(tuple(self.capability_ids)),
        )


@dataclass(frozen=True, slots=True)
class ToolCapabilityCatalog(ValueObject):
    requirements: tuple[ToolCapabilityRequirement, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        by_id: dict[str, ToolCapabilityRequirement] = {}
        for requirement in self.requirements:
            if requirement.id in by_id:
                raise ToolValidationError(
                    f"Duplicate tool capability id '{requirement.id}'.",
                )
            by_id[requirement.id] = requirement
        object.__setattr__(self, "requirements", tuple(by_id.values()))

    @classmethod
    def default(cls) -> "ToolCapabilityCatalog":
        return cls(
            requirements=tuple(
                ToolCapabilityRequirement(
                    id=capability_id,
                    label=label,
                    description=description,
                )
                for capability_id, label, description in _DEFAULT_CAPABILITY_DESCRIPTIONS
            ),
        )

    @property
    def capability_ids(self) -> tuple[str, ...]:
        return tuple(requirement.id for requirement in self.requirements)

    def requirement_for(self, capability_id: str) -> ToolCapabilityRequirement:
        normalized_id = _normalize_capability_id(capability_id)
        for requirement in self.requirements:
            if requirement.id == normalized_id:
                return requirement
        raise ToolValidationError(f"Unknown tool capability '{normalized_id}'.")

    def validate_capability_ids(self, capability_ids: tuple[str, ...]) -> tuple[str, ...]:
        normalized_ids = _normalize_capability_ids(capability_ids)
        for capability_id in normalized_ids:
            self.requirement_for(capability_id)
        return normalized_ids

    def validate_manifest(
        self,
        manifest: ToolPackageCapabilityManifest,
    ) -> ToolPackageCapabilityManifest:
        self.validate_capability_ids(manifest.capability_ids)
        return manifest

    def manifest_for(
        self,
        *,
        package_id: str,
        capability_ids: tuple[str, ...],
    ) -> ToolPackageCapabilityManifest:
        manifest = ToolPackageCapabilityManifest(
            package_id=package_id,
            capability_ids=capability_ids,
        )
        return self.validate_manifest(manifest)


DEFAULT_TOOL_CAPABILITY_CATALOG = ToolCapabilityCatalog.default()
TOOL_CAPABILITY_IDS = DEFAULT_TOOL_CAPABILITY_CATALOG.capability_ids
