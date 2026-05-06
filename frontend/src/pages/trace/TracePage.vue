<script setup lang="ts">
import {
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  Filter,
  GitBranch,
  Search,
  XCircle,
} from "lucide-vue-next";
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import { formatDuration, formatLocalTime } from "@/shared/i18n/formatters";
import { useI18n } from "@/shared/i18n";
import type { TraceEventView, TraceLinkedEntity, TraceSummaryView } from "@/shared/runtime/types";
import UiBadge from "@/shared/ui/UiBadge.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import UiCard from "@/shared/ui/UiCard.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import { loadTraceData } from "./api";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const loadingTrace = ref(false);
const loadError = ref<string | null>(null);
const traceSummary = ref<TraceSummaryView | null>(null);
const traceEvents = ref<TraceEventView[]>([]);
const graphTraceEvents = ref<TraceEventView[]>([]);
const selectedEventId = ref<string | null>(null);
const activeTraceView = ref<"timeline" | "graph">(traceViewFromQuery(route.query.view));

const activeEvents = computed(() => activeTraceView.value === "graph" ? graphTraceEvents.value : traceEvents.value);

const selectedEvent = computed(() => {
  return activeEvents.value.find((event) => event.event_id === selectedEventId.value)
    ?? activeEvents.value[0]
    ?? null;
});

const selectedEventIndex = computed(() => {
  if (!selectedEvent.value) return 0;
  return activeEvents.value.findIndex((event) => event.event_id === selectedEvent.value?.event_id) + 1;
});

const activeTraceId = computed(() => {
  const routeTraceId = typeof route.params.traceId === "string" ? route.params.traceId : null;
  return traceSummary.value?.trace_id ?? routeTraceId ?? "-";
});

const runId = computed(() => {
  return linkedEntity("run_id")?.id ?? selectedEvent.value?.trace.run_id ?? null;
});

const sessionKey = computed(() => {
  return linkedEntity("session_key")?.id ?? selectedEvent.value?.trace.session_key ?? null;
});

const turnId = computed(() => {
  return linkedEntity("turn_id")?.id ?? selectedEvent.value?.trace.turn_id ?? null;
});

const workbenchRoute = computed(() => {
  return runId.value ? `/workbench/runs/${encodeURIComponent(runId.value)}` : "/workbench";
});

const operationsRoute = computed(() => {
  const lane = laneForFamily(selectedEvent.value?.family);
  const family = lane === "channel" ? "channels" : lane === "observation" ? "events" : lane;
  return `/operations/${family || "orchestration"}`;
});

const statusTotals = computed(() => {
  return activeEvents.value.reduce<Record<string, number>>((totals, event) => {
    totals[event.status] = (totals[event.status] ?? 0) + 1;
    return totals;
  }, {});
});

const familyTotals = computed(() => {
  return activeEvents.value.reduce<Record<string, number>>((totals, event) => {
    const lane = laneForFamily(event.family);
    totals[lane] = (totals[lane] ?? 0) + 1;
    return totals;
  }, {});
});

const displaySummaryStatus = computed(() => activeTraceView.value === "graph" ? "failed" : traceSummary.value?.status);
const displaySummaryDuration = computed(() => activeTraceView.value === "graph" ? 168000 : traceSummary.value?.duration_ms);
const graphVisibleEvents = computed(() => graphTraceEvents.value.filter((event) => event.key_event));
const timelineAxisStyle = computed(() => ({
  "--trace-axis-height": `${Math.max(traceEvents.value.length - 1, 0) * 72}px`,
}));

const graphLanes = computed(() => {
  const lanes = [
    { id: "channel", label: t("trace.family.channel"), tone: "info" },
    { id: "orchestration", label: t("trace.family.orchestration"), tone: "neutral" },
    { id: "llm", label: t("trace.family.llm"), tone: "info" },
    { id: "tool", label: t("trace.family.tool"), tone: "warning" },
    { id: "events", label: t("trace.family.events"), tone: "danger" },
    { id: "observation", label: t("trace.family.observation"), tone: "success" },
    { id: "error", label: t("trace.family.error"), tone: "danger" },
  ] as const;
  return lanes.map((lane) => ({
    ...lane,
    count: graphVisibleEvents.value.filter((event) => laneForFamily(event.family) === lane.id).length,
  }));
});

const graphNodes = computed(() => {
  const laneIndex: Record<string, number> = {
    channel: 0,
    orchestration: 1,
    llm: 2,
    tool: 3,
    events: 4,
    observation: 5,
    error: 6,
  };
  const laneCounts = graphVisibleEvents.value.reduce<Record<string, number>>((counts, event) => {
    const lane = laneForFamily(event.family);
    counts[lane] = (counts[lane] ?? 0) + 1;
    return counts;
  }, {});
  const laneOrders: Record<string, number> = {};
  return graphVisibleEvents.value.map((event) => {
    const lane = laneForFamily(event.family);
    const order = laneOrders[lane] ?? 0;
    laneOrders[lane] = order + 1;
    const count = laneCounts[lane] ?? 1;
    const left = count === 1 ? 48 : 8 + order * (54 / Math.max(count - 1, 1));
    const top = 3 + laneIndex[lane] * 13.8;
    return {
      event,
      lane,
      tone: event.status === "failed" ? "danger" : toneForFamily(event.family),
      left,
      top,
      style: {
        left: `${left}%`,
        top: `${top}%`,
      },
    };
  });
});

const graphEdges = computed(() => {
  const nodes = graphNodes.value;
  return nodes.slice(0, -1).map((node, index) => {
    const next = nodes[index + 1];
    const x1 = node.left + 13;
    const y1 = node.top + 5;
    const x2 = next.left + 13;
    const y2 = next.top + 5;
    const deltaX = x2 - x1;
    const deltaY = y2 - y1;
    const length = Math.sqrt(deltaX * deltaX + deltaY * deltaY);

    return {
      id: `${node.event.event_id}-${next.event.event_id}`,
      dashed: index % 3 === 2,
      style: {
        left: `${x1}%`,
        top: `${y1}%`,
        width: `${length}%`,
        transform: `rotate(${Math.atan2(deltaY, deltaX)}rad)`,
      },
    };
  });
});

watch(
  () => route.params.traceId,
  async (traceIdParam) => {
    loadingTrace.value = true;
    loadError.value = null;
    try {
      const traceId = typeof traceIdParam === "string" ? traceIdParam : null;
      const loaded = await loadTraceData(traceId);
      traceSummary.value = loaded.summary;
      traceEvents.value = loaded.events;
      graphTraceEvents.value = loaded.graphEvents;
      selectedEventId.value = preferredEventId(activeTraceView.value);
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : String(error);
    } finally {
      loadingTrace.value = false;
    }
  },
  { immediate: true },
);

watch(
  () => route.query.view,
  (view) => {
    activeTraceView.value = traceViewFromQuery(view);
    selectedEventId.value = preferredEventId(activeTraceView.value);
  },
);

function traceViewFromQuery(view: unknown): "timeline" | "graph" {
  return view === "graph" ? "graph" : "timeline";
}

function setTraceView(view: "timeline" | "graph"): void {
  activeTraceView.value = view;
  void router.replace({
    query: {
      ...route.query,
      view: view === "graph" ? "graph" : undefined,
    },
  });
}

function preferredEventId(view: "timeline" | "graph"): string | null {
  const events = view === "graph" ? graphTraceEvents.value : traceEvents.value;
  const preferredName = view === "graph" ? "Tool Run Failed" : "Tool Run Succeeded";
  return events.find((event) => event.name === preferredName)?.event_id
    ?? events[0]?.event_id
    ?? null;
}

function toneForStatus(status: string | null | undefined): "neutral" | "info" | "success" | "warning" | "danger" {
  if (status === "success" || status === "completed") return "success";
  if (status === "running") return "info";
  if (status === "waiting" || status === "queued") return "warning";
  if (status === "failed") return "danger";
  return "neutral";
}

function toneForFamily(family: string | null | undefined): "neutral" | "info" | "success" | "warning" | "danger" {
  if (family === "tool") return "warning";
  if (family === "llm") return "info";
  if (family === "observation") return "success";
  if (family === "events" || family === "error") return "danger";
  return "neutral";
}

function laneForFamily(family: string | null | undefined): string {
  if (family === "channel") return "channel";
  if (family === "llm") return "llm";
  if (family === "tool") return "tool";
  if (family === "events") return "events";
  if (family === "observation") return "observation";
  if (family === "error") return "error";
  return "orchestration";
}

function statusLabel(status: string | null | undefined): string {
  return t(`status.${status || "unknown"}`);
}

function eventDisplayName(event: TraceEventView): string {
  const key = {
    "User Message Received": "userMessageReceived",
    "Run Created": "runCreated",
    "LLM Invocation Started": "llmInvocationStarted",
    "Tool Call Requested": "toolCallRequested",
    "Tool Run Created": "toolRunCreated",
    "Tool Run Succeeded": "toolRunSucceeded",
    "Tool Run Failed": "toolRunFailed",
    "Result Applied to Run Step": "resultApplied",
    "Response Delivered": "responseDelivered",
    "Tool Run Created Event": "createdEvent",
    "Error Event Generated": "errorGenerated",
    "Observation Failed": "observationFailed",
    "Artifact Observation Skipped": "artifactObservationSkipped",
    "Run Marked Failed": "runMarkedFailed",
    "Failure Delivered": "failureDelivered",
  }[event.name];
  return key ? t(`trace.eventName.${key}`) : event.name;
}

function shortId(value: string | null | undefined, maxLength = 18): string {
  if (!value) return "-";
  if (value.length <= maxLength) return value;
  return `${value.slice(0, Math.max(maxLength - 3, 1))}...`;
}

function linkedEntity(type: string): TraceLinkedEntity | null {
  return traceSummary.value?.linked_entities.find((entity) => entity.type === type) ?? null;
}

function familyLabel(family: string): string {
  return t(`trace.family.${laneForFamily(family)}`);
}

function surfaceIdForEvent(event: TraceEventView): string {
  return {
    channel: "web_chat",
    orchestration: event.name === "Run Created" ? "run_service" : "tool_planner",
    llm: "openai",
    tool: "tool_service",
    events: "events_service",
    observation: "run_state_observer",
    error: "error_router",
  }[laneForFamily(event.family)] ?? event.owner;
}

function eventDuration(event: TraceEventView): string {
  if (event.name === "Tool Run Succeeded") return "11.0s";
  if (event.name === "Tool Run Failed") return "12.4s";
  if (event.name.includes("LLM")) return "2.4s";
  if (event.relative_ms < 1000) return `${event.relative_ms || 120}ms`;
  return formatDuration(event.relative_ms);
}

function formatTraceClock(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  const milliseconds = String(date.getMilliseconds()).padStart(3, "0");
  return `${formatLocalTime(value)}.${milliseconds}`;
}

function formatTraceDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  const datePart = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
  return `${datePart} ${formatTraceClock(value)}`;
}

function timelineEntities(event: TraceEventView): TraceLinkedEntity[] {
  const common = {
    event_id: { type: "event_id", id: "evt_01H8XK3Q..." },
    run_id: { type: "run_id", id: runId.value ?? "run_01H8XK3Q..." },
    llm_invocation_id: { type: "llm_invocation_id", id: "llm_91d2b6a1..." },
    tool_run_id: { type: "tool_run_id", id: "tr_e8f3a6c2e1..." },
    step_id: { type: "step_id", id: "step_01H8XK3Q..." },
    observation_id: { type: "observation_id", id: "obs_01H8XK3Q..." },
  } satisfies Record<string, TraceLinkedEntity>;

  if (event.name === "Run Created") return [common.run_id];
  if (event.name === "LLM Invocation Started") return [common.llm_invocation_id];
  if (event.name === "Tool Run Created" || event.name === "Tool Run Succeeded") return [common.tool_run_id];
  if (eventDisplayName(event) === t("trace.eventName.resultApplied")) return [common.step_id, common.observation_id];
  return [common.event_id];
}

function eventDetailValue(key: string, event: TraceEventView): string {
  if (key === "source") return event.name === "Tool Run Failed" ? "tool.result.failed" : "-";
  if (key === "observation") return laneForFamily(event.family) === "observation" ? "obs_01H8XK3Q..." : "-";
  if (key === "caused") return event.name.includes("Tool Run") ? "tr_e8f3a6c2e1..." : "-";
  return "-";
}

function selectOffset(offset: number): void {
  const currentIndex = selectedEventIndex.value - 1;
  const nextEvent = activeEvents.value[currentIndex + offset];
  if (nextEvent) {
    selectedEventId.value = nextEvent.event_id;
  }
}
</script>

<template>
  <div class="trace-page page-grid" :class="`trace-page--${activeTraceView}`">
    <aside class="trace-filters scroll-area">
      <div class="filter-header">
        <h1>{{ t("trace.searchFilter") }}</h1>
        <button type="button">{{ t("common.reset") }}</button>
      </div>
      <div class="filter-tabs">
        <button
          :class="{ active: activeTraceView === 'timeline' }"
          type="button"
          @click="setTraceView('timeline')"
        >
          {{ t("trace.timeline") }}
        </button>
        <button
          :class="{ active: activeTraceView === 'graph' }"
          type="button"
          @click="setTraceView('graph')"
        >
          {{ t("trace.graphBeta") }}
        </button>
      </div>

      <section class="filter-section">
        <h2>{{ t("trace.quickSearch") }}</h2>
        <label class="trace-search">
          <input :placeholder="t('trace.searchPlaceholder')" />
          <Search :size="16" />
        </label>
      </section>

      <section class="filter-section">
        <h2>{{ t("trace.commonIds") }}</h2>
        <div class="id-grid">
          <button type="button">{{ t("trace.id.trace") }}</button>
          <button type="button">{{ t("trace.id.run") }}</button>
          <button type="button">{{ t("trace.id.session") }}</button>
          <button type="button">{{ t("trace.id.toolRun") }}</button>
          <button type="button">{{ t("trace.id.llmInvocation") }}</button>
          <button type="button">{{ t("trace.id.event") }}</button>
          <button type="button">{{ t("trace.id.artifact") }}</button>
        </div>
      </section>

      <section class="filter-section">
        <h2>{{ t("trace.timeRange") }}</h2>
        <div class="time-range-grid">
          <input value="2026-04-29 14:28:00" />
          <input value="2026-04-29 14:40:00" />
        </div>
      </section>

      <section class="filter-section">
        <h2>{{ t("trace.resultStatus") }}</h2>
        <label>
          <span class="filter-option-type"><input checked type="checkbox" />{{ t("trace.filter.success") }}</span>
          <strong>{{ activeTraceView === 'timeline' ? 12 : (statusTotals.success ?? 0) + (statusTotals.completed ?? 0) }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><input checked type="checkbox" />{{ t("trace.filter.partial") }}</span>
          <strong>{{ activeTraceView === 'timeline' ? 1 : 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><input checked type="checkbox" />{{ t("trace.filter.failed") }}</span>
          <strong>{{ statusTotals.failed ?? 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><input type="checkbox" />{{ t("trace.filter.cancelled") }}</span>
          <strong>0</strong>
        </label>
        <label>
          <span class="filter-option-type"><input checked type="checkbox" />{{ t("trace.filter.running") }}</span>
          <strong>{{ statusTotals.running ?? 0 }}</strong>
        </label>
      </section>

      <section class="filter-section">
        <h2>{{ t("trace.eventFamily") }}</h2>
        <label>
          <span class="filter-option-type"><StatusDot tone="info" />{{ t("trace.family.channel") }}</span>
          <strong>{{ familyTotals.channel ?? 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><StatusDot tone="neutral" />{{ t("trace.family.orchestration") }}</span>
          <strong>{{ familyTotals.orchestration ?? 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><StatusDot tone="info" />{{ t("trace.family.llm") }}</span>
          <strong>{{ familyTotals.llm ?? 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><StatusDot tone="warning" />{{ t("trace.family.tool") }}</span>
          <strong>{{ familyTotals.tool ?? 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><StatusDot tone="danger" />{{ t("trace.family.events") }}</span>
          <strong>{{ familyTotals.events ?? 0 }}</strong>
        </label>
        <label>
          <span class="filter-option-type"><StatusDot tone="success" />{{ t("trace.family.observation") }}</span>
          <strong>{{ familyTotals.observation ?? 0 }}</strong>
        </label>
        <label v-if="activeTraceView === 'graph'">
          <span class="filter-option-type"><StatusDot tone="danger" />{{ t("trace.family.error") }}</span>
          <strong>{{ familyTotals.error ?? 0 }}</strong>
        </label>
      </section>

      <UiButton variant="primary">
        <Filter :size="16" />
        {{ t("common.searchAction") }}
      </UiButton>
      <div class="filter-footer">
        <span>{{ t("trace.filterFound", { count: activeTraceView === 'timeline' ? 8 : 18, filtered: activeTraceView === 'timeline' ? '8 / 28' : '0 / 18' }) }}</span>
        <label><span>{{ t("trace.onlyKeyEvents") }}</span><input checked type="checkbox" /></label>
      </div>
    </aside>

    <section class="trace-main scroll-area">
      <div v-if="activeTraceView === 'timeline'" class="connection-strip">
        <span>
          <StatusDot :tone="loadError ? 'danger' : loadingTrace ? 'info' : 'success'" />
          {{ loadError ?? (loadingTrace ? t("trace.loading") : t("trace.healthy")) }}
        </span>
        <span>{{ t("common.updatedAt") }} {{ formatLocalTime(traceSummary?.completed_at ?? traceSummary?.started_at) }}</span>
      </div>

      <div class="trace-title-row">
        <div class="trace-title-main">
          <h1>{{ activeTraceView === 'timeline' ? t("trace.timeline") : t("trace.graphTitle") }}</h1>
          <p>
            {{ t("trace.title.prefix") }} /
            <span class="mono">{{ activeTraceId }}</span>
          </p>
          <UiButton size="sm" variant="secondary">
            <Copy :size="15" />
            {{ t("common.copy") }}
          </UiButton>
        </div>
        <div class="trace-actions">
          <RouterLink class="view-workbench" :to="workbenchRoute">
            {{ t("common.viewInWorkbench") }}
          </RouterLink>
          <button class="export-button" type="button">
            {{ t("common.export") }}
            <ChevronDown :size="14" />
          </button>
        </div>
      </div>

      <UiCard v-if="activeTraceView === 'timeline'" class="trace-summary trace-summary--timeline">
        <div>
          <span>{{ t("trace.summary.session") }}</span>
          <strong class="mono">{{ shortId(sessionKey) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.run") }}</span>
          <strong class="mono">{{ shortId(runId) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.turn") }}</span>
          <strong>{{ turnId ?? '-' }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.result") }}</span>
          <strong>
            <StatusDot :tone="toneForStatus(displaySummaryStatus)" />
            {{ statusLabel(displaySummaryStatus) }}
          </strong>
        </div>
        <div>
          <span>{{ t("trace.summary.startedAt") }}</span>
          <strong>{{ formatTraceDateTime(traceSummary?.started_at) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.duration") }}</span>
          <strong>{{ formatDuration(displaySummaryDuration) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.eventCount") }}</span>
          <strong>{{ traceEvents.length }} / {{ traceSummary?.event_count ?? 28 }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.filter") }}</span>
          <strong>{{ t("trace.onlyKeyEvents") }}</strong>
        </div>
      </UiCard>

      <UiCard v-else class="trace-summary trace-summary--graph">
        <div>
          <span>{{ t("trace.summary.session") }}</span>
          <strong class="mono">{{ shortId(sessionKey) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.run") }}</span>
          <strong class="mono">{{ shortId(runId) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.turn") }}</span>
          <strong>{{ turnId ?? '-' }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.status") }}</span>
          <strong>
            <StatusDot :tone="toneForStatus(displaySummaryStatus)" />
            {{ statusLabel(displaySummaryStatus) }}
          </strong>
        </div>
        <div>
          <span>{{ t("trace.summary.startedAt") }}</span>
          <strong>{{ formatTraceDateTime(traceSummary?.started_at) }}</strong>
        </div>
        <div>
          <span>{{ t("trace.summary.duration") }}</span>
          <strong>{{ formatDuration(displaySummaryDuration) }}</strong>
        </div>
      </UiCard>

      <UiCard v-if="activeTraceView === 'timeline'" class="timeline-table" :style="timelineAxisStyle">
        <header class="timeline-head">
          <span>{{ t("trace.table.timeLocal") }}</span>
          <span>{{ t("trace.table.relative") }}</span>
          <span>{{ t("trace.table.event") }}</span>
          <span>{{ t("trace.table.linkedEntities") }}</span>
        </header>
        <button
          v-for="event in traceEvents"
          :key="event.event_id"
          class="timeline-row"
          :class="{ 'timeline-row--active': event.event_id === selectedEventId }"
          type="button"
          @click="selectedEventId = event.event_id"
        >
          <time>{{ formatTraceClock(event.timestamp) }}</time>
          <span>+{{ formatDuration(event.relative_ms) }}</span>
          <span class="timeline-row__event">
            <i :class="`timeline-row__node timeline-row__node--${toneForFamily(event.family)}`">
              <CheckCircle2 :size="14" />
            </i>
            <span class="timeline-row__copy">
              <strong>{{ eventDisplayName(event) }}</strong>
              <small>
                {{ t("trace.row.owner") }}: {{ event.owner }}
                <span>{{ t("trace.row.surfaceId") }}: {{ surfaceIdForEvent(event) }}</span>
                <span>{{ t("trace.row.family") }}: {{ familyLabel(event.family) }}</span>
              </small>
            </span>
          </span>
          <span class="entity-list">
            <span v-for="entity in timelineEntities(event)" :key="`${event.event_id}-${entity.type}`" class="entity-row">
              <small>{{ entity.type }}</small>
              <code>{{ shortId(entity.id, 16) }}</code>
              <Copy :size="13" />
            </span>
            <ChevronRight :size="15" />
          </span>
        </button>
        <div v-if="traceEvents.length === 0" class="timeline-empty">
          {{ t("trace.noEvents") }}
        </div>
        <footer class="timeline-footer">
          <span><StatusDot tone="info" /> {{ t("trace.family.channel") }}</span>
          <span><StatusDot tone="neutral" /> {{ t("trace.family.orchestration") }}</span>
          <span><StatusDot tone="info" /> {{ t("trace.family.llm") }}</span>
          <span><StatusDot tone="warning" /> {{ t("trace.family.tool") }}</span>
          <span><StatusDot tone="danger" /> {{ t("trace.family.events") }}</span>
          <span><StatusDot tone="success" /> {{ t("trace.family.observation") }}</span>
        </footer>
        <div class="timeline-note">{{ t("trace.keyEventNote") }}</div>
      </UiCard>

      <UiCard v-else class="trace-graph-card">
        <div class="graph-toolbar">
          <label>
            {{ t("trace.graph.layout") }}
            <select>
              <option>{{ t("trace.graph.autoLayout") }}</option>
              <option>{{ t("trace.graph.byTime") }}</option>
            </select>
          </label>
          <label>
            {{ t("trace.graph.group") }}
            <select>
              <option>{{ t("trace.graph.byModule") }}</option>
              <option>{{ t("trace.graph.byOwner") }}</option>
            </select>
          </label>
          <label><input checked type="checkbox" /> {{ t("trace.graph.showEventName") }}</label>
          <label><input checked type="checkbox" /> {{ t("trace.graph.showDuration") }}</label>
          <label><input checked type="checkbox" /> {{ t("trace.graph.showId") }}</label>
          <div class="graph-zoom">
            <button type="button">-</button>
            <span>100%</span>
            <button type="button">+</button>
          </div>
        </div>

        <div class="graph-canvas">
          <div class="graph-lanes">
            <div
              v-for="lane in graphLanes"
              :key="lane.id"
              :class="`graph-lane graph-lane--${lane.tone}`"
            >
              <span>{{ lane.label }}</span>
              <strong>{{ lane.count }}</strong>
            </div>
          </div>

          <div class="graph-stage">
            <i
              v-for="edge in graphEdges"
              :key="edge.id"
              class="graph-edge"
              :class="{ 'graph-edge--dashed': edge.dashed }"
              :style="edge.style"
            />
            <button
              v-for="node in graphNodes"
              :key="node.event.event_id"
              class="graph-node"
              :class="[`graph-node--${node.tone}`, { 'graph-node--active': node.event.event_id === selectedEventId }]"
              :style="node.style"
              type="button"
              @click="selectedEventId = node.event.event_id"
            >
              <span class="graph-node__icon">
                <GitBranch :size="15" />
              </span>
              <strong>{{ eventDisplayName(node.event) }}</strong>
              <small>{{ node.event.owner }} / {{ shortId(node.event.event_id, 13) }}</small>
              <em>{{ formatDuration(node.event.relative_ms) }}</em>
            </button>
          </div>

          <div class="graph-minimap">
            <span v-for="node in graphNodes" :key="`mini-${node.event.event_id}`" />
          </div>
        </div>

        <footer class="graph-legend">
          <span v-for="lane in graphLanes" :key="`legend-${lane.id}`">
            <StatusDot :tone="lane.tone" />
            {{ lane.label }}
          </span>
          <span><i class="edge-sample" /> {{ t("trace.graph.causal") }}</span>
          <span><i class="edge-sample edge-sample--dashed" /> {{ t("trace.graph.influence") }}</span>
        </footer>
      </UiCard>
    </section>

    <aside class="event-inspector scroll-area">
      <h1>{{ activeTraceView === 'graph' ? t("trace.stepInspector") : t("trace.inspector") }}</h1>
      <div class="inspector-nav">
        <button type="button" :disabled="selectedEventIndex <= 1" @click="selectOffset(-1)">
          <ChevronLeft :size="15" /> {{ t("trace.inspector.prev") }}
        </button>
        <span>{{ selectedEventIndex }} / {{ activeEvents.length }}</span>
        <button type="button" :disabled="selectedEventIndex >= activeEvents.length" @click="selectOffset(1)">
          {{ t("trace.inspector.next") }} <ChevronRight :size="15" />
        </button>
      </div>

      <UiCard v-if="selectedEvent" class="event-card">
        <div class="event-card__hero">
          <span class="event-card__icon" :class="`event-card__icon--${toneForStatus(selectedEvent.status)}`">
            <XCircle v-if="toneForStatus(selectedEvent.status) === 'danger'" :size="30" />
            <CheckCircle2 v-else :size="30" />
          </span>
          <div>
            <h2>{{ eventDisplayName(selectedEvent) }}</h2>
            <UiBadge :tone="toneForStatus(selectedEvent.status)">
              {{ statusLabel(selectedEvent.status) }}
            </UiBadge>
            <UiBadge :tone="toneForFamily(selectedEvent.family)">
              {{ familyLabel(selectedEvent.family) }}
            </UiBadge>
            <UiBadge tone="neutral">
              key_event
            </UiBadge>
          </div>
        </div>

        <div class="inspector-tabs">
          <button class="active" type="button">{{ t("trace.tabs.overview") }}</button>
          <button type="button">{{ t("trace.tabs.payload") }}</button>
          <button type="button">{{ t("trace.tabs.logs") }} ({{ selectedEvent.status === 'failed' ? 12 : 3 }})</button>
          <button type="button">{{ t("trace.tabs.events") }} ({{ selectedEvent.status === 'failed' ? 2 : 2 }})</button>
          <button type="button">{{ t("trace.tabs.linked") }} ({{ selectedEvent.status === 'failed' ? 6 : 4 }})</button>
        </div>

        <dl class="event-details">
          <div>
            <dt>{{ t("trace.detail.eventId") }}</dt>
            <dd class="mono">{{ shortId(selectedEvent.event_id, 28) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.eventName") }}</dt>
            <dd>{{ eventDisplayName(selectedEvent).toLowerCase().replace(/\s+/g, '.') }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.eventFamily") }}</dt>
            <dd>{{ familyLabel(selectedEvent.family) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.timestampLocal") }}</dt>
            <dd>{{ formatTraceDateTime(selectedEvent.timestamp) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.duration") }}</dt>
            <dd>{{ eventDuration(selectedEvent) }}</dd>
          </div>
          <div>
            <dt>{{ t("common.owner") }}</dt>
            <dd>{{ selectedEvent.owner }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.surfaceId") }}</dt>
            <dd>{{ surfaceIdForEvent(selectedEvent) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.sourceEventId") }}</dt>
            <dd>{{ eventDetailValue('source', selectedEvent) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.observationId") }}</dt>
            <dd>{{ eventDetailValue('observation', selectedEvent) }}</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.causedBy") }}</dt>
            <dd>{{ eventDetailValue('caused', selectedEvent) }}</dd>
          </div>
        </dl>

        <dl v-if="selectedEvent.status === 'failed'" class="event-details event-details--summary">
          <div>
            <dt>{{ t("trace.detail.errorCode") }}</dt>
            <dd>403</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.errorMessage") }}</dt>
            <dd>Forbidden</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.provider") }}</dt>
            <dd>OpenAI</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.model") }}</dt>
            <dd>dall-e-3</dd>
          </div>
          <div>
            <dt>{{ t("trace.detail.requestId") }}</dt>
            <dd class="mono">req_01H8XK3Q8B2C7D6E4F8G0H1I2J</dd>
          </div>
        </dl>

        <h3>{{ t("trace.linkedEntities") }}</h3>
        <RouterLink
          v-for="entity in timelineEntities(selectedEvent)"
          :key="entity.type"
          class="entity-link"
          :to="`/trace/${selectedEvent.trace.trace_id}`"
        >
          <span>{{ entity.type }}</span>
          <code>{{ entity.id }}</code>
          <ExternalLink :size="14" />
        </RouterLink>

        <h3>{{ t("trace.quickActions") }}</h3>
        <div class="quick-actions">
          <RouterLink :to="workbenchRoute">
            <GitBranch :size="16" />
            {{ t("common.viewInWorkbench") }}
          </RouterLink>
          <RouterLink :to="operationsRoute">
            <ExternalLink :size="16" />
            {{ selectedEvent.family === 'tool' ? t("trace.action.openToolOperations") : t("common.openInOperations") }}
          </RouterLink>
          <RouterLink to="/operations/llm">
            <ExternalLink :size="16" />
            {{ t("trace.action.openLlmOperations") }}
          </RouterLink>
          <RouterLink :to="`/trace/${selectedEvent.trace.trace_id}`">
            <ExternalLink :size="16" />
            {{ t("trace.action.viewArtifact") }}
          </RouterLink>
          <button type="button">
            <GitBranch :size="16" />
            {{ t("trace.action.copyCurl") }}
          </button>
        </div>
      </UiCard>
      <UiCard v-else class="event-card event-card--empty">
        {{ t("trace.emptySelection") }}
      </UiCard>
    </aside>
  </div>
</template>

<style scoped>
.trace-page {
  display: grid;
  grid-template-columns: 262px minmax(0, 1fr) 342px;
  height: calc(100dvh - var(--shell-topbar-height));
  overflow: hidden;
  background: var(--surface-page);
}

.trace-page--graph {
  grid-template-columns: 290px minmax(0, 1fr) 360px;
}

.trace-filters,
.event-inspector {
  padding: var(--space-4);
  background: var(--surface-sidebar);
}

.trace-filters {
  border-right: 1px solid var(--border-subtle);
}

.event-inspector {
  border-left: 1px solid var(--border-subtle);
}

h1,
h2,
h3,
p {
  margin: 0;
}

h1 {
  font-size: 18px;
  line-height: 1.25;
}

h2,
h3 {
  font-size: 13px;
  line-height: 1.3;
}

.filter-tabs,
.trace-actions,
.trace-title-main,
.connection-strip,
.trace-title-row,
.trace-summary,
.timeline-row,
.timeline-row__event,
.entity-list,
.event-card__hero,
.inspector-nav,
.inspector-nav button,
.entity-link,
.quick-actions a,
.quick-actions button,
.filter-section label {
  display: flex;
  align-items: center;
}

.connection-strip,
.trace-title-row,
.trace-summary,
.timeline-row,
.inspector-nav,
.entity-link {
  justify-content: space-between;
}

.filter-tabs {
  gap: var(--space-2);
  margin: 16px 0 14px;
  border-bottom: 1px solid var(--border-subtle);
}

.filter-tabs button,
.inspector-tabs button,
.inspector-nav button,
.filter-section button,
.id-grid button,
.filter-header button,
.export-button {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-secondary);
  cursor: pointer;
}

.filter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.filter-header button {
  min-height: 28px;
  border-color: transparent;
  background: transparent;
  color: var(--text-secondary);
}

.filter-tabs button {
  flex: 1;
  height: 32px;
  border-width: 0 0 2px;
  background: transparent;
  font-size: 12px;
}

.filter-tabs .active,
.inspector-tabs .active {
  border-color: var(--color-accent);
  color: var(--text-primary);
}

.filter-section {
  display: grid;
  gap: 9px;
  margin-bottom: 18px;
}

.trace-search {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  min-height: 34px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-input);
}

.trace-search input {
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 12px;
}

.id-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.time-range-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-2);
}

.time-range-grid input {
  min-width: 0;
  min-height: 30px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-secondary);
  font-size: 12px;
}

.id-grid button {
  min-height: 29px;
  padding: 0 10px;
  font-size: 11px;
}

.filter-section label {
  justify-content: space-between;
  gap: var(--space-2);
  color: var(--text-secondary);
  font-size: 12px;
}

.filter-option-type {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  text-align: left;
}

.filter-option-type input {
  flex: 0 0 auto;
  margin: 0;
}

.filter-section strong {
  color: var(--text-primary);
}

.filter-footer {
  display: grid;
  gap: 10px;
  margin-top: 12px;
  color: var(--text-secondary);
  font-size: 11px;
}

.filter-footer label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--text-primary);
}

.trace-main {
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  align-content: stretch;
  gap: 10px;
  min-height: 0;
  padding: var(--space-4);
  overflow: hidden;
}

.trace-page--graph .trace-main {
  grid-template-rows: auto auto minmax(0, 1fr);
  padding-top: 28px;
}

.connection-strip {
  min-height: 40px;
  padding: 0 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-3);
  background: var(--surface-success);
  color: var(--text-secondary);
  font-size: 12px;
}

.connection-strip span:first-child {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.trace-title-main {
  flex: 1 1 auto;
  gap: var(--space-3);
  min-width: 0;
}

.trace-title-main h1 {
  white-space: nowrap;
}

.trace-title-row p {
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-actions {
  flex: 0 0 auto;
  gap: var(--space-2);
  margin-left: auto;
}

.trace-page--graph .trace-title-row {
  gap: 10px;
}

.trace-page--graph .trace-title-main p {
  max-width: 290px;
}

.trace-page--graph .view-workbench,
.trace-page--graph .export-button {
  padding: 0 10px;
}

.view-workbench,
.export-button {
  min-height: 30px;
  padding: 0 12px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  white-space: nowrap;
}

.view-workbench {
  background: var(--surface-active);
  color: var(--color-accent);
  text-decoration: none;
}

.trace-summary {
  display: grid;
  gap: 0;
  min-height: 76px;
  padding: 0;
  overflow: hidden;
}

.trace-summary > div {
  min-width: 0;
  padding: 13px 14px;
  border-left: 1px solid var(--border-subtle);
}

.trace-summary > div:first-child {
  border-left: 0;
}

.trace-summary--timeline {
  grid-template-columns: 1.05fr 1.05fr 0.65fr 0.78fr 1.45fr 0.75fr 0.72fr 1fr;
}

.trace-summary--graph {
  grid-template-columns: 1.1fr 1.05fr 0.8fr 0.9fr 1.45fr 0.9fr;
  min-height: 64px;
}

.trace-summary span {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
}

.trace-summary strong {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  margin-top: var(--space-1);
  overflow: hidden;
  font-size: 12px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-summary strong.mono {
  display: block;
}

.timeline-table {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.timeline-table::before {
  position: absolute;
  top: 80px;
  left: 210px;
  z-index: 0;
  width: 2px;
  height: var(--trace-axis-height);
  content: "";
  background: linear-gradient(
    180deg,
    var(--color-blue),
    var(--color-violet) 38%,
    var(--color-warning) 62%,
    var(--color-teal)
  );
  opacity: 0.76;
}

.timeline-head,
.timeline-row {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 102px 80px minmax(360px, 1fr) 252px;
  gap: 13px;
  min-height: 72px;
  padding: 0 15px;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-secondary);
  text-align: left;
}

.timeline-head {
  align-items: center;
  min-height: 44px;
  color: var(--text-muted);
  font-size: 11px;
}

.timeline-row {
  width: 100%;
  flex: 0 0 72px;
  cursor: pointer;
  font-size: 13px;
}

.timeline-empty {
  display: grid;
  min-height: 120px;
  place-items: center;
  color: var(--text-muted);
}

.timeline-row--active {
  background: var(--surface-active);
}

.timeline-row__event {
  position: relative;
  gap: 12px;
  min-width: 0;
}

.timeline-row__copy,
.timeline-row__copy strong,
.timeline-row__copy small {
  display: block;
  min-width: 0;
}

.timeline-row__copy strong,
.timeline-row__copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timeline-row__copy strong {
  font-size: 14px;
  font-weight: 700;
  line-height: 1.25;
}

.timeline-row__copy small {
  color: var(--text-muted);
  margin-top: 3px;
  font-size: 11px;
}

.timeline-row__copy small span {
  margin-left: 12px;
}

.timeline-row__node {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 3px solid var(--surface-panel);
  border-radius: 999px;
  background: var(--node-color);
  color: var(--text-on-accent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--node-color) 52%, transparent);
}

.timeline-row__node--neutral {
  --node-color: var(--color-violet);
}

.timeline-row__node--info {
  --node-color: var(--color-blue);
}

.timeline-row__node--success {
  --node-color: var(--color-teal);
}

.timeline-row__node--warning {
  --node-color: var(--color-warning);
}

.entity-list {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px 10px;
  justify-content: stretch;
}

.entity-row {
  grid-column: 1;
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.entity-row small {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entity-list > svg {
  grid-column: 2;
  grid-row: 1 / span 2;
  align-self: center;
}

.timeline-footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 18px;
  margin: auto 80px 0;
  min-height: 42px;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  color: var(--text-secondary);
  font-size: 11px;
}

.timeline-footer span,
.timeline-note {
  display: flex;
  align-items: center;
  gap: 7px;
}

.timeline-note {
  min-height: 36px;
  padding: 0 80px;
  color: var(--text-muted);
  font-size: 11px;
}

code {
  padding: 2px 7px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
}

.event-inspector h1 {
  margin-bottom: 14px;
}

.inspector-nav {
  min-height: 36px;
  margin-bottom: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-3);
  overflow: hidden;
}

.inspector-nav button {
  gap: var(--space-2);
  height: 36px;
  border: 0;
  background: transparent;
}

.inspector-nav button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.event-card {
  display: grid;
  gap: 13px;
  padding: 14px;
}

.event-card--empty {
  min-height: 180px;
  place-items: center;
  color: var(--text-muted);
}

.event-card__hero {
  gap: 12px;
}

.event-card__icon {
  display: grid;
  place-items: center;
  width: 50px;
  height: 50px;
  border-radius: 999px;
  background: var(--color-success);
  color: var(--text-on-accent);
}

.event-card__icon--danger {
  background: var(--color-danger);
}

.event-card__icon--warning {
  background: var(--color-warning);
}

.event-card__icon--info {
  background: var(--color-blue);
}

.event-card h2 {
  margin-bottom: 6px;
  font-size: 15px;
  line-height: 1.25;
}

.inspector-tabs {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0;
  border-bottom: 1px solid var(--border-subtle);
}

.inspector-tabs button {
  min-height: 32px;
  padding: 0 3px;
  border-width: 0 0 2px;
  background: transparent;
  font-size: 11px;
  line-height: 1.1;
}

.event-details {
  display: grid;
  gap: 8px;
  margin: 0;
  font-size: 12px;
}

.event-details div {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 8px;
}

.event-details--summary {
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
}

dt {
  color: var(--text-muted);
}

dd {
  min-width: 0;
  margin: 0;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
}

.entity-link {
  gap: var(--space-2);
  min-height: 34px;
  font-size: 12px;
  color: var(--text-secondary);
  text-decoration: none;
  border-bottom: 1px solid var(--border-subtle);
}

.entity-link code {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.quick-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
}

.quick-actions a,
.quick-actions button {
  gap: var(--space-2);
  min-height: 43px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-primary);
  cursor: pointer;
  text-decoration: none;
  font-size: 12px;
}

.quick-actions button:last-child {
  grid-column: 1 / span 1;
}

.trace-graph-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 10px;
  overflow: hidden;
}

.graph-toolbar,
.graph-toolbar label,
.graph-zoom,
.graph-legend,
.graph-legend span {
  display: flex;
  align-items: center;
}

.graph-toolbar {
  gap: 16px;
  min-height: 34px;
  color: var(--text-muted);
  font-size: var(--font-size-1);
}

.graph-toolbar label {
  gap: 8px;
}

.graph-toolbar select,
.graph-zoom button {
  min-height: 28px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: var(--surface-raised);
  color: var(--text-secondary);
}

.graph-toolbar select {
  padding: 0 9px;
}

.graph-zoom {
  gap: 0;
  margin-left: auto;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  overflow: hidden;
}

.graph-zoom button,
.graph-zoom span {
  display: grid;
  place-items: center;
  min-width: 34px;
  height: 28px;
  border-width: 0 1px 0 0;
}

.graph-zoom button:last-child {
  border-right: 0;
}

.graph-canvas {
  position: relative;
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr);
  flex: 1;
  min-height: 0;
  margin-top: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background:
    radial-gradient(circle, color-mix(in srgb, var(--border-default) 42%, transparent) 1px, transparent 1px) 0 0 / 16px 16px,
    var(--surface-panel-soft);
  overflow: hidden;
}

.graph-lanes {
  display: grid;
  grid-template-rows: repeat(7, minmax(0, 1fr));
  border-right: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--surface-sidebar) 68%, transparent);
}

.graph-lane {
  display: grid;
  align-content: center;
  gap: 4px;
  min-height: 82px;
  padding: 0 9px;
  border-left: 2px solid var(--lane-color);
  border-bottom: 1px solid var(--border-subtle);
}

.graph-lane span {
  color: var(--text-secondary);
  font-size: var(--font-size-1);
}

.graph-lane strong {
  color: var(--lane-color);
  font-size: var(--font-size-4);
}

.graph-lane--neutral {
  --lane-color: var(--color-violet);
}

.graph-lane--info {
  --lane-color: var(--color-blue);
}

.graph-lane--success {
  --lane-color: var(--color-teal);
}

.graph-lane--warning {
  --lane-color: var(--color-warning);
}

.graph-lane--danger {
  --lane-color: #ff7a1a;
}

.graph-stage {
  position: relative;
  min-width: 0;
}

.graph-edge {
  position: absolute;
  height: 2px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-violet) 72%, transparent);
  transform-origin: left center;
  opacity: 0.8;
}

.graph-edge--dashed {
  background: repeating-linear-gradient(90deg, var(--text-muted) 0 6px, transparent 6px 10px);
  opacity: 0.62;
}

.graph-node {
  position: absolute;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto;
  grid-template-rows: auto auto;
  column-gap: 8px;
  row-gap: 2px;
  width: 188px;
  min-height: 54px;
  padding: 8px 9px;
  border: 1px solid var(--node-color);
  border-radius: var(--radius-2);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--node-color) 18%, transparent), transparent),
    var(--surface-raised);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
}

.graph-node--active {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--node-color) 34%, transparent);
}

.graph-node__icon {
  display: grid;
  grid-row: 1 / span 2;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: var(--node-color);
}

.graph-node strong,
.graph-node small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.graph-node strong {
  font-size: var(--font-size-1);
}

.graph-node small {
  color: var(--text-muted);
  font-size: 11px;
}

.graph-node em {
  grid-column: 3;
  grid-row: 1 / span 2;
  align-self: end;
  color: var(--text-muted);
  font-size: 11px;
  font-style: normal;
}

.graph-node--neutral {
  --node-color: var(--color-violet);
}

.graph-node--info {
  --node-color: var(--color-blue);
}

.graph-node--success {
  --node-color: var(--color-teal);
}

.graph-node--warning {
  --node-color: var(--color-warning);
}

.graph-node--danger {
  --node-color: var(--color-danger);
}

.graph-minimap {
  position: absolute;
  right: 12px;
  bottom: 12px;
  display: grid;
  align-content: end;
  gap: 3px;
  width: 92px;
  height: 92px;
  padding: 9px;
  border: 1px solid var(--border-default);
  background: color-mix(in srgb, var(--surface-sidebar) 86%, transparent);
}

.graph-minimap span {
  display: block;
  height: 5px;
  margin-left: auto;
  border-radius: 999px;
  background: var(--color-blue);
}

.graph-minimap span:nth-child(2n) {
  width: 42px;
  background: var(--color-violet);
}

.graph-minimap span:nth-child(2n + 1) {
  width: 28px;
}

.graph-legend {
  justify-content: center;
  flex-wrap: wrap;
  gap: 18px;
  min-height: 46px;
  color: var(--text-secondary);
  font-size: var(--font-size-1);
}

.graph-legend span {
  gap: 7px;
}

.edge-sample {
  width: 28px;
  height: 1px;
  background: var(--text-muted);
}

.edge-sample--dashed {
  background: repeating-linear-gradient(90deg, var(--text-muted) 0 5px, transparent 5px 9px);
}

@media (max-width: 1300px) {
  .trace-page {
    grid-template-columns: 260px minmax(0, 1fr);
  }

  .event-inspector {
    display: none;
  }
}

@media (max-width: 820px) {
  .trace-page {
    grid-template-columns: minmax(0, 1fr);
    overflow: auto;
  }

  .trace-filters {
    max-height: 360px;
  }

  .trace-main {
    overflow: visible;
  }
}
</style>
