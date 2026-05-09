import { computed, ref, shallowRef, unref, watch, type Ref } from "vue";

import {
  getSettingsResource,
  loadSettingsReadModel,
  normalizeSettingsResourceId,
  runSettingsAction,
  type SettingsActionOptions,
  type SettingsPaginationParams,
  type SettingsResourceRouteAlias,
} from "./api";
import type {
  SettingsActionName,
  SettingsActionResponse,
  SettingsAuditRecord,
  SettingsDetailReadModel,
  SettingsPayload,
  SettingsReadModel,
  SettingsResourceKind,
  SettingsResourceSummary,
} from "@/shared/runtime/types";

export type SettingsPageResourceItem = SettingsResourceSummary | SettingsAuditRecord;
export type SettingsResourceSource = SettingsResourceRouteAlias | Ref<SettingsResourceRouteAlias>;

export interface UseSettingsPageOptions {
  pagination?: SettingsPaginationParams;
  immediate?: boolean;
}

export function useSettingsPage(
  resource: SettingsResourceSource,
  options: UseSettingsPageOptions = {},
) {
  const page = shallowRef<SettingsReadModel | null>(null);
  const detail = shallowRef<SettingsDetailReadModel | null>(null);
  const selectedResourceId = ref<string | null>(null);
  const loading = ref(false);
  const detailLoading = ref(false);
  const actionLoading = ref(false);
  const error = ref<string | null>(null);
  const stale = ref(false);
  const pagination = ref<SettingsPaginationParams>({
    limit: options.pagination?.limit ?? 50,
    offset: options.pagination?.offset ?? 0,
  });

  const activeResource = computed(() => normalizeSettingsResourceId(unref(resource)));
  const activeKind = computed<SettingsResourceKind | null>(() => (
    activeResource.value === "overview" ? null : activeResource.value
  ));
  const isOverview = computed(() => activeResource.value === "overview");
  const resources = computed<SettingsPageResourceItem[]>(() => {
    const current = page.value;
    return current && current.resource !== "overview" ? current.resources : [];
  });
  const empty = computed(() => {
    const current = page.value;
    if (!current) return false;
    if (current.resource === "overview") return current.counts.resources === 0;
    return current.status === "empty" || current.resources.length === 0;
  });
  const total = computed(() => (
    page.value && page.value.resource !== "overview"
      ? page.value.list.total ?? page.value.resources.length
      : 0
  ));

  let requestVersion = 0;

  async function load(
    nextPagination: SettingsPaginationParams = pagination.value,
  ): Promise<SettingsReadModel> {
    const requestId = ++requestVersion;
    loading.value = true;
    error.value = null;
    pagination.value = { ...pagination.value, ...nextPagination };

    try {
      const nextPage = await loadSettingsReadModel(activeResource.value, pagination.value);
      if (requestId === requestVersion) {
        page.value = nextPage;
        stale.value = false;
        if (nextPage.resource === "overview") {
          detail.value = null;
          selectedResourceId.value = null;
        } else {
          detail.value = nextPage.detail;
          selectedResourceId.value =
            detailId(nextPage.detail) ?? itemId(nextPage.resources[0]) ?? null;
        }
      }
      return nextPage;
    } catch (caught) {
      if (requestId === requestVersion) {
        error.value = errorMessage(caught);
      }
      throw caught;
    } finally {
      if (requestId === requestVersion) {
        loading.value = false;
      }
    }
  }

  async function refresh(): Promise<SettingsReadModel> {
    return load(pagination.value);
  }

  async function setPagination(nextPagination: SettingsPaginationParams): Promise<SettingsReadModel> {
    return load({ ...pagination.value, ...nextPagination });
  }

  async function selectResource(resourceId: string): Promise<SettingsDetailReadModel | null> {
    const kind = activeKind.value;
    if (!kind) return null;

    detailLoading.value = true;
    error.value = null;
    selectedResourceId.value = resourceId;
    try {
      const nextDetail = await getSettingsResource(kind, resourceId);
      detail.value = nextDetail;
      return nextDetail;
    } catch (caught) {
      error.value = errorMessage(caught);
      throw caught;
    } finally {
      detailLoading.value = false;
    }
  }

  async function runAction(
    action: SettingsActionName,
    payload: SettingsPayload = {},
    reason: string | null = null,
    resourceId: string | null = selectedResourceId.value,
    actionOptions: SettingsActionOptions = {},
  ): Promise<SettingsActionResponse> {
    const kind = activeKind.value;
    if (!kind) {
      throw new Error("Settings overview does not support resource actions.");
    }

    actionLoading.value = true;
    error.value = null;
    try {
      const response = await runSettingsAction(
        kind,
        resourceId,
        action,
        payload,
        reason,
        actionOptions,
      );
      stale.value = true;
      await refresh();
      return response;
    } catch (caught) {
      error.value = errorMessage(caught);
      throw caught;
    } finally {
      actionLoading.value = false;
    }
  }

  watch(
    activeResource,
    () => {
      if (options.immediate === false) return;
      void load({ ...pagination.value, offset: 0 });
    },
    { immediate: options.immediate !== false },
  );

  return {
    actionLoading,
    activeKind,
    activeResource,
    detail,
    detailLoading,
    empty,
    error,
    isOverview,
    load,
    loading,
    page,
    pagination,
    refresh,
    resources,
    runAction,
    selectResource,
    selectedResourceId,
    setPagination,
    stale,
    total,
  };
}

function detailId(detail: SettingsDetailReadModel | null): string | null {
  if (!detail) return null;
  return "audit_id" in detail ? detail.audit_id : detail.resource_id;
}

function itemId(item: SettingsPageResourceItem | undefined): string | null {
  if (!item) return null;
  return "audit_id" in item ? item.audit_id : item.resource_id;
}

function errorMessage(value: unknown): string {
  return value instanceof Error ? value.message : String(value);
}
