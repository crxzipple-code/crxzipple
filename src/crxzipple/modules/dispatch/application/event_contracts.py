from __future__ import annotations

from crxzipple.modules.dispatch.application.observers import dispatch_wakeup_topic
from crxzipple.modules.events import EventTopicContract
from crxzipple.shared import (
    EventDefinition,
    EventDefinitionField,
    EventObserver,
    EventSurface,
)


def dispatch_event_topic_contracts() -> tuple[EventTopicContract, ...]:
    return (
        EventTopicContract(
            contract_id="dispatch.wakeup",
            topic_pattern=dispatch_wakeup_topic("{owner_kind}"),
            owner="dispatch",
            description=(
                "Wakeup command topic used to interrupt idle worker waits when "
                "new dispatch work becomes available."
            ),
            kinds=("command",),
            producers=("DispatchWakeupObserver",),
            consumers=("worker_loops._wait_for_dispatch_wakeup",),
            durability="persistent",
            ordering="owner_id",
            notes=(
                "workers still claim work from the database",
                "this topic is a wake signal, not the task source of truth",
            ),
        ),
    )


def dispatch_event_definitions() -> tuple[EventDefinition, ...]:
    fields = (
        EventDefinitionField(
            "event_name",
            "Dispatch source event name that triggered the wakeup command.",
            "string",
            True,
        ),
        EventDefinitionField(
            "owner_kind",
            "Dispatch owner kind that should wake up.",
            "string",
            True,
        ),
        EventDefinitionField(
            "owner_id",
            "Optional owning entity id used for ordering and scoping.",
            "string",
        ),
        EventDefinitionField(
            "lane_key",
            "Optional lane key carried from the dispatch task.",
            "string",
        ),
    )
    return tuple(
        EventDefinition(
            definition_id=event_name,
            owner="dispatch",
            event_name=event_name,
            description=(
                "Dispatch wakeup command observed from a dispatch task lifecycle "
                "event."
            ),
            topics=("dispatch.wakeup.{owner_kind}",),
            producers=("DispatchWakeupObserver",),
            consumers=("worker_loops._wait_for_dispatch_wakeup",),
            fields=fields,
            durability="persistent",
            publication_mode="reduced",
            source_event_names=(event_name,),
            notes=(
                "This command is a wake signal only; workers still claim authoritative work from the database.",
            ),
        )
        for event_name in (
            "dispatch.task.queued",
            "dispatch.task.requeued",
            "dispatch.task.recovered",
        )
    )


def dispatch_event_surfaces() -> tuple[EventSurface, ...]:
    return (
        EventSurface(
            surface_id="dispatch.wakeup",
            owner="dispatch",
            description="Dispatch wakeup command surface for idle worker loops.",
            definition_ids=(
                "dispatch.task.queued",
                "dispatch.task.requeued",
                "dispatch.task.recovered",
            ),
            topics=("dispatch.wakeup.{owner_kind}",),
            consumers=("worker_loops._wait_for_dispatch_wakeup",),
            notes=(
                "Wakeup commands are observed from dispatch task lifecycle events.",
            ),
        ),
    )


def dispatch_event_observers() -> tuple[EventObserver, ...]:
    return (
        EventObserver(
            observer_id="dispatch.wakeup",
            owner="dispatch",
            description=(
                "Observes dispatch task lifecycle source events into wakeup "
                "commands for idle worker loops."
            ),
            source_event_names=(
                "dispatch.task.queued",
                "dispatch.task.requeued",
                "dispatch.task.recovered",
            ),
            output_definition_ids=(
                "dispatch.task.queued",
                "dispatch.task.requeued",
                "dispatch.task.recovered",
            ),
            handlers=(
                "DispatchWakeupObserver.observe_task_queued",
                "DispatchWakeupObserver.observe_task_requeued",
                "DispatchWakeupObserver.observe_task_recovered",
            ),
            notes=(
                "Reduces dispatch lifecycle facts into wakeup commands without changing the bus transport path.",
            ),
        ),
    )
