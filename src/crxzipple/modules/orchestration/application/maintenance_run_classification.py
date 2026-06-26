from __future__ import annotations

from crxzipple.modules.orchestration.application.runtime_request_mode import (
    RuntimeRequestMode,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun


class OrchestrationMaintenanceRunClassificationMixin:
    @staticmethod
    def is_context_limit_error(exc: Exception) -> bool:
        message = (str(exc) or type(exc).__name__).strip().lower()
        if not message:
            return False
        patterns = (
            "context length",
            "context_length",
            "maximum context",
            "max context",
            "context window",
            "too many tokens",
            "token limit",
            "prompt is too long",
            "context_limit",
        )
        return any(pattern in message for pattern in patterns)

    def is_maintenance_mode_run(self, run: OrchestrationRun) -> bool:
        if self.is_memory_flush_run(run):
            return True
        if self.is_compaction_run(run):
            return True
        runtime_request_mode = _runtime_request_mode_value(run)
        if runtime_request_mode == RuntimeRequestMode.HEARTBEAT.value:
            return True
        runtime_request_flow_hint = run.metadata.get("runtime_request_flow_hint")
        if isinstance(runtime_request_flow_hint, dict):
            raw_mode = _flow_hint_mode_value(runtime_request_flow_hint)
            if raw_mode == RuntimeRequestMode.HEARTBEAT.value:
                return True
        return False

    @staticmethod
    def is_memory_flush_run(run: OrchestrationRun) -> bool:
        runtime_request_mode = _runtime_request_mode_value(run)
        if runtime_request_mode == RuntimeRequestMode.MEMORY_FLUSH.value:
            return True
        if run.inbound_instruction.source == "memory_flush":
            return True
        runtime_request_flow_hint = run.metadata.get("runtime_request_flow_hint")
        if isinstance(runtime_request_flow_hint, dict):
            raw_mode = _flow_hint_mode_value(runtime_request_flow_hint)
            if raw_mode == RuntimeRequestMode.MEMORY_FLUSH.value:
                return True
        return False

    @staticmethod
    def is_compaction_run(run: OrchestrationRun) -> bool:
        runtime_request_mode = _runtime_request_mode_value(run)
        if runtime_request_mode == RuntimeRequestMode.COMPACTION.value:
            return True
        if run.inbound_instruction.source == "compaction":
            return True
        runtime_request_flow_hint = run.metadata.get("runtime_request_flow_hint")
        if isinstance(runtime_request_flow_hint, dict):
            raw_mode = _flow_hint_mode_value(runtime_request_flow_hint)
            if raw_mode == RuntimeRequestMode.COMPACTION.value:
                return True
        return False


def _runtime_request_mode_value(run: OrchestrationRun) -> str:
    return str(run.metadata.get("runtime_request_mode", "")).strip().lower()


def _flow_hint_mode_value(payload: dict[object, object]) -> str:
    return str(payload.get("mode", "")).strip().lower()
