import { onMounted, onUnmounted } from "vue";

import type { OperationsRefreshEvent } from "./api";

export type OperationsModuleId =
  | "orchestration"
  | "tool"
  | "browser"
  | "llm"
  | "access"
  | "channels"
  | "memory"
  | "skills"
  | "events"
  | "daemon";

interface OperationsProjectionRefreshOptions {
  delayMs?: number;
  isEnabled?: () => boolean;
}

const OPERATIONS_EVENT_NAME = "crxzipple:operations-event";
const DEFAULT_REFRESH_DELAY_MS = 150;

export function useOperationsProjectionRefresh(
  moduleId: OperationsModuleId,
  refresh: () => void | Promise<void>,
  options: OperationsProjectionRefreshOptions = {},
) {
  let refreshTimer: number | null = null;

  function clearRefreshTimer() {
    if (refreshTimer === null) return;
    window.clearTimeout(refreshTimer);
    refreshTimer = null;
  }

  function scheduleRefresh() {
    if (options.isEnabled?.() === false) return;
    if (refreshTimer !== null) return;
    refreshTimer = window.setTimeout(() => {
      refreshTimer = null;
      void refresh();
    }, options.delayMs ?? DEFAULT_REFRESH_DELAY_MS);
  }

  function handleProjectionEvent(event: Event) {
    const record = (event as CustomEvent<OperationsRefreshEvent>).detail;
    if (!record || !recordAppliesToModule(record, moduleId)) return;
    scheduleRefresh();
  }

  onMounted(() => {
    window.addEventListener(OPERATIONS_EVENT_NAME, handleProjectionEvent);
  });

  onUnmounted(() => {
    window.removeEventListener(OPERATIONS_EVENT_NAME, handleProjectionEvent);
    clearRefreshTimer();
  });

  return {
    scheduleRefresh,
    clearRefreshTimer,
  };
}

function recordAppliesToModule(record: OperationsRefreshEvent, moduleId: OperationsModuleId): boolean {
  if (record.module === moduleId) return true;
  return Array.isArray(record.modules) && record.modules.includes(moduleId);
}
