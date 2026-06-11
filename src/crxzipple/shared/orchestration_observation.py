from __future__ import annotations

SESSION_MESSAGE_APPENDED_SOURCE_EVENT = "session.message.appended"
ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT = "orchestration.run.message.appended"
ORCHESTRATION_RUN_QUEUED_EVENT = "orchestration.run.queued"
ORCHESTRATION_RUN_CLAIMED_EVENT = "orchestration.run.claimed"
ORCHESTRATION_RUN_ADVANCED_EVENT = "orchestration.run.advanced"
ORCHESTRATION_RUN_LLM_ATTEMPT_REWOUND_EVENT = "orchestration.run.llm_attempt_rewound"
ORCHESTRATION_RUN_WAITING_EVENT = "orchestration.run.waiting"
ORCHESTRATION_RUN_WAITING_FOR_CONFIRMATION_EVENT = (
    "orchestration.run.waiting_for_confirmation"
)
ORCHESTRATION_RUN_APPROVAL_RESOLVED_EVENT = "orchestration.run.approval_resolved"
ORCHESTRATION_RUN_WORKER_LEASE_RECOVERED_EVENT = (
    "orchestration.run.worker_lease_recovered"
)
ORCHESTRATION_RUN_RESUMED_EVENT = "orchestration.run.resumed"
ORCHESTRATION_RUN_COMPLETED_EVENT = "orchestration.run.completed"
ORCHESTRATION_RUN_FAILED_EVENT = "orchestration.run.failed"
ORCHESTRATION_RUN_CANCELLED_EVENT = "orchestration.run.cancelled"
ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT = "orchestration.run.llm_text_delta"
ORCHESTRATION_RUN_TOOL_UPDATED_EVENT = "orchestration.run.tool.updated"
ORCHESTRATION_RUNTIME_STATUS_EVENT = "orchestration.runtime.status"

ORCHESTRATION_RUN_OBSERVATION_EVENT_NAMES: tuple[str, ...] = (
    ORCHESTRATION_RUN_QUEUED_EVENT,
    ORCHESTRATION_RUN_CLAIMED_EVENT,
    ORCHESTRATION_RUN_ADVANCED_EVENT,
    ORCHESTRATION_RUN_LLM_ATTEMPT_REWOUND_EVENT,
    ORCHESTRATION_RUN_WAITING_EVENT,
    ORCHESTRATION_RUN_WAITING_FOR_CONFIRMATION_EVENT,
    ORCHESTRATION_RUN_APPROVAL_RESOLVED_EVENT,
    ORCHESTRATION_RUN_WORKER_LEASE_RECOVERED_EVENT,
    ORCHESTRATION_RUN_RESUMED_EVENT,
    ORCHESTRATION_RUN_COMPLETED_EVENT,
    ORCHESTRATION_RUN_FAILED_EVENT,
    ORCHESTRATION_RUN_CANCELLED_EVENT,
)

TOOL_RUN_OBSERVATION_SOURCE_EVENT_NAMES: tuple[str, ...] = (
    "tool.run.created",
    "tool.run.queued",
    "tool.run.dispatching",
    "tool.run.started",
    "tool.run.succeeded",
    "tool.run.failed",
    "tool.run.requeued",
    "tool.run.cancel_requested",
    "tool.run.cancelled",
    "tool.run.timed_out",
)

ORCHESTRATION_RUNTIME_OBSERVATION_SOURCE_EVENT_NAMES: tuple[str, ...] = (
    ORCHESTRATION_RUN_QUEUED_EVENT,
    ORCHESTRATION_RUN_CLAIMED_EVENT,
    ORCHESTRATION_RUN_WAITING_EVENT,
    ORCHESTRATION_RUN_WAITING_FOR_CONFIRMATION_EVENT,
    ORCHESTRATION_RUN_WORKER_LEASE_RECOVERED_EVENT,
    ORCHESTRATION_RUN_RESUMED_EVENT,
    ORCHESTRATION_RUN_COMPLETED_EVENT,
    ORCHESTRATION_RUN_FAILED_EVENT,
    ORCHESTRATION_RUN_CANCELLED_EVENT,
    "orchestration.executor.lease.registered",
    "orchestration.executor.lease.heartbeated",
    "orchestration.executor.lease.assignment_claimed",
    "orchestration.executor.lease.assignment_released",
    "orchestration.executor.lease.offline",
)
