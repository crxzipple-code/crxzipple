from __future__ import annotations

RUN_ACCEPTED_EVENT = "orchestration.run.accepted"
RUN_ROUTED_EVENT = "orchestration.run.routed"
RUN_BULK_READY_EVENT = "orchestration.run.bulk_ready"
RUN_QUEUED_EVENT = "orchestration.run.queued"
RUN_CLAIMED_EVENT = "orchestration.run.claimed"
RUN_HEARTBEATED_EVENT = "orchestration.run.heartbeated"
RUN_ADVANCED_EVENT = "orchestration.run.advanced"
RUN_LLM_ATTEMPT_REWOUND_EVENT = "orchestration.run.llm_attempt_rewound"
RUN_WAITING_EVENT = "orchestration.run.waiting"
RUN_WAITING_FOR_CONFIRMATION_EVENT = "orchestration.run.waiting_for_confirmation"
RUN_APPROVAL_RESOLVED_EVENT = "orchestration.run.approval_resolved"
RUN_WORKER_LEASE_RECOVERED_EVENT = "orchestration.run.worker_lease_recovered"
RUN_RESUMED_EVENT = "orchestration.run.resumed"
RUN_COMPLETED_EVENT = "orchestration.run.completed"
RUN_FAILED_EVENT = "orchestration.run.failed"
RUN_CANCELLED_EVENT = "orchestration.run.cancelled"

INGRESS_REQUESTED_EVENT = "orchestration.ingress.requested"
INGRESS_CLAIMED_EVENT = "orchestration.ingress.claimed"
INGRESS_COMPLETED_EVENT = "orchestration.ingress.completed"
INGRESS_FAILED_EVENT = "orchestration.ingress.failed"

EXECUTOR_ASSIGNMENT_REQUESTED_EVENT = "orchestration.executor.assignment.requested"
EXECUTOR_LEASE_REGISTERED_EVENT = "orchestration.executor.lease.registered"
EXECUTOR_LEASE_HEARTBEATED_EVENT = "orchestration.executor.lease.heartbeated"
EXECUTOR_LEASE_ASSIGNMENT_CLAIMED_EVENT = (
    "orchestration.executor.lease.assignment_claimed"
)
EXECUTOR_LEASE_ASSIGNMENT_RELEASED_EVENT = (
    "orchestration.executor.lease.assignment_released"
)
EXECUTOR_LEASE_OFFLINE_EVENT = "orchestration.executor.lease.offline"

ORPHAN_TOOL_RESULT_OBSERVED_EVENT = (
    "orchestration.execution.orphan_tool_result_observed"
)

RUNTIME_STATUS_EVENT = "orchestration.runtime.status"

ORCHESTRATION_OPERATIONAL_EVENT_NAMES: tuple[str, ...] = (
    RUN_ACCEPTED_EVENT,
    RUN_ROUTED_EVENT,
    RUN_BULK_READY_EVENT,
    RUN_QUEUED_EVENT,
    RUN_CLAIMED_EVENT,
    RUN_HEARTBEATED_EVENT,
    RUN_ADVANCED_EVENT,
    RUN_LLM_ATTEMPT_REWOUND_EVENT,
    RUN_WAITING_EVENT,
    RUN_WAITING_FOR_CONFIRMATION_EVENT,
    RUN_APPROVAL_RESOLVED_EVENT,
    RUN_WORKER_LEASE_RECOVERED_EVENT,
    RUN_RESUMED_EVENT,
    RUN_COMPLETED_EVENT,
    RUN_FAILED_EVENT,
    RUN_CANCELLED_EVENT,
    INGRESS_REQUESTED_EVENT,
    INGRESS_CLAIMED_EVENT,
    INGRESS_COMPLETED_EVENT,
    INGRESS_FAILED_EVENT,
    EXECUTOR_ASSIGNMENT_REQUESTED_EVENT,
    EXECUTOR_LEASE_REGISTERED_EVENT,
    EXECUTOR_LEASE_HEARTBEATED_EVENT,
    EXECUTOR_LEASE_ASSIGNMENT_CLAIMED_EVENT,
    EXECUTOR_LEASE_ASSIGNMENT_RELEASED_EVENT,
    EXECUTOR_LEASE_OFFLINE_EVENT,
    ORPHAN_TOOL_RESULT_OBSERVED_EVENT,
    RUNTIME_STATUS_EVENT,
)
