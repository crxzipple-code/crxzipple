<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { CheckCircle2, PlayCircle, Power, ShieldCheck } from "lucide-vue-next";

import { useI18n } from "@/shared/i18n";
import type { SettingsActionResponse, SettingsResourceKind } from "@/shared/runtime/types";
import UiButton from "@/shared/ui/UiButton.vue";
import { runSettingsAction, settingsActionRequiresReason } from "../api";
import {
  settingsActionPolicyFor,
  type RunnableSettingsAction,
} from "../settingsActionPolicy";

const props = withDefaults(
  defineProps<{
    kind: SettingsResourceKind;
    resourceId?: string | null;
    enabled?: boolean | null;
    actor?: string | null;
  }>(),
  {
    resourceId: null,
    enabled: null,
    actor: "settings-ui",
  },
);

const emit = defineEmits<{
  completed: [response: SettingsActionResponse];
}>();

const { t } = useI18n();

const selectedAction = ref<RunnableSettingsAction>("validate");
const reason = ref("");
const isSubmitting = ref(false);
const errorMessage = ref<string | null>(null);
const successMessage = ref<string | null>(null);

const normalizedResourceId = computed(() => props.resourceId?.trim() || null);
const actionPolicy = computed(() => settingsActionPolicyFor(props.kind));
const requiresReason = computed(() => settingsActionRequiresReason(selectedAction.value));
const reasonIsMissing = computed(
  () => requiresReason.value && reason.value.trim().length === 0,
);
const canSubmit = computed(
  () => actionOptions.value.length > 0
    && Boolean(normalizedResourceId.value)
    && !isSubmitting.value
    && !reasonIsMissing.value,
);
const actionOptions = computed<Array<{ value: RunnableSettingsAction; label: string }>>(() => [
  ...actionPolicy.value.actions
    .filter((action) => action === "validate" || action === "dry-run")
    .map((action) => ({
      value: action,
      label: t(`settings.action.${actionKey(action)}`),
    })),
  ...(
    actionPolicy.value.actions.includes("enable") || actionPolicy.value.actions.includes("disable")
      ? [{
          value: props.enabled === false ? "enable" as const : "disable" as const,
          label: props.enabled === false ? t("settings.action.enable") : t("settings.action.disable"),
        }]
      : []
  ),
]);
const submitTone = computed(() =>
  selectedAction.value === "disable" ? "danger" : selectedAction.value === "enable" ? "primary" : "secondary",
);
const hasRunnableActions = computed(() => actionOptions.value.length > 0);

watch(
  () => props.enabled,
  () => {
    const options = actionOptions.value.map((option) => option.value);
    if (!options.includes(selectedAction.value)) {
      selectedAction.value = options[0] ?? "validate";
    } else if (selectedAction.value === "enable" && props.enabled !== false) {
      selectedAction.value = "disable";
    } else if (selectedAction.value === "disable" && props.enabled === false) {
      selectedAction.value = "enable";
    }
  },
);

watch(
  actionOptions,
  (options) => {
    if (!options.some((option) => option.value === selectedAction.value)) {
      selectedAction.value = options[0]?.value ?? "validate";
    }
  },
  { immediate: true },
);

watch(selectedAction, () => {
  errorMessage.value = null;
  successMessage.value = null;
});

async function submitAction(): Promise<void> {
  errorMessage.value = null;
  successMessage.value = null;
  const resourceId = normalizedResourceId.value;
  if (!resourceId) {
    errorMessage.value = t("settings.actionPanel.noResource");
    return;
  }
  if (reasonIsMissing.value) {
    errorMessage.value = t("settings.actionPanel.reasonRequired");
    return;
  }

  isSubmitting.value = true;
  try {
    const response = await runSettingsAction(
      props.kind,
      resourceId,
      selectedAction.value,
      {},
      reason.value,
      {
        actor: props.actor ?? "settings-ui",
        risk: requiresReason.value ? "medium" : "low",
        dry_run: selectedAction.value === "dry-run",
        metadata: {
          source: "settings_action_panel",
        },
      },
    );
    successMessage.value = t("settings.actionPanel.success", {
      action: t(`settings.action.${actionKey(selectedAction.value)}`),
    });
    if (!requiresReason.value) {
      reason.value = "";
    }
    emit("completed", response);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error);
  } finally {
    isSubmitting.value = false;
  }
}

function actionKey(action: RunnableSettingsAction): string {
  return action === "dry-run" ? "dryRun" : action;
}
</script>

<template>
  <article class="settings-panel settings-action-panel">
    <div class="settings-panel-heading">
      <h2><ShieldCheck :size="16" />{{ t("settings.actionPanel.title") }}</h2>
      <span>{{ normalizedResourceId ?? t("settings.actionPanel.noResourceShort") }}</span>
    </div>

    <p>{{ t("settings.actionPanel.description") }}</p>
    <dl class="settings-action-policy">
      <div>
        <dt>{{ t("settings.actionPanel.owner") }}</dt>
        <dd>{{ t(actionPolicy.ownerKey) }}</dd>
      </div>
      <div>
        <dt>{{ t("settings.actionPanel.truthSource") }}</dt>
        <dd>{{ t(actionPolicy.truthSourceKey) }}</dd>
      </div>
      <div>
        <dt>{{ t("settings.actionPanel.applyPolicy") }}</dt>
        <dd>{{ t(actionPolicy.applyPolicyKey) }}</dd>
      </div>
    </dl>
    <p class="settings-action-policy-note">{{ t(actionPolicy.descriptionKey) }}</p>

    <form v-if="hasRunnableActions" class="settings-action-form" @submit.prevent="submitAction">
      <label>
        <span>{{ t("settings.actionPanel.action") }}</span>
        <select v-model="selectedAction">
          <option v-for="option in actionOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>

      <label>
        <span>
          {{ t("settings.actionPanel.reason") }}
          <em v-if="requiresReason">{{ t("settings.actionPanel.required") }}</em>
        </span>
        <textarea
          v-model="reason"
          rows="3"
          :placeholder="t('settings.actionPanel.reasonPlaceholder')"
        />
      </label>

      <div class="settings-action-controls">
        <UiButton :variant="submitTone" size="sm" type="submit" :disabled="!canSubmit">
          <CheckCircle2 v-if="selectedAction === 'validate'" :size="14" />
          <PlayCircle v-else-if="selectedAction === 'dry-run'" :size="14" />
          <Power v-else :size="14" />
          {{ isSubmitting ? t("settings.actionPanel.submitting") : t("settings.actionPanel.submit") }}
        </UiButton>
      </div>
    </form>
    <p v-else class="settings-action-readonly">
      {{ t("settings.actionPanel.readonlyNoActions") }}
    </p>

    <p v-if="errorMessage" class="settings-action-feedback settings-action-feedback--danger">
      {{ errorMessage }}
    </p>
    <p v-else-if="successMessage" class="settings-action-feedback settings-action-feedback--success">
      {{ successMessage }}
    </p>
  </article>
</template>

<style scoped>
.settings-action-panel {
  display: grid;
  gap: 10px;
}

.settings-action-panel h2 {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.settings-action-panel p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.settings-action-policy {
  display: grid;
  gap: 1px;
  margin: 0;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
}

.settings-action-policy div {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  min-height: 30px;
  padding: 7px 9px;
  background: color-mix(in srgb, var(--surface-base) 78%, transparent);
}

.settings-action-policy dt,
.settings-action-policy dd {
  min-width: 0;
  margin: 0;
  font-size: 11px;
  line-height: 1.35;
}

.settings-action-policy dt {
  color: var(--text-muted);
  font-weight: 700;
}

.settings-action-policy dd {
  color: var(--text-primary);
}

.settings-action-policy-note,
.settings-action-readonly {
  padding: 7px 9px;
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--color-info) 10%, transparent);
}

.settings-action-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 8px;
}

.settings-action-form label {
  display: grid;
  gap: 5px;
  min-width: 0;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
}

.settings-action-form label:nth-of-type(2) {
  grid-column: 1 / -1;
}

.settings-action-form label > span {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.settings-action-form em {
  color: var(--color-warning);
  font-style: normal;
  font-size: 10px;
}

.settings-action-form select,
.settings-action-form textarea {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-base) 90%, transparent);
  color: var(--text-primary);
  font: inherit;
}

.settings-action-form select {
  min-height: 32px;
  padding: 0 9px;
}

.settings-action-form textarea {
  min-height: 52px;
  max-height: 90px;
  resize: vertical;
  padding: 8px 9px;
}

.settings-action-controls {
  display: flex;
  justify-content: flex-end;
  min-width: 78px;
}

.settings-action-feedback {
  border-radius: var(--radius-2);
  padding: 7px 9px;
  font-size: 11px;
  font-weight: 700;
}

.settings-action-feedback--danger {
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  color: var(--color-danger);
}

.settings-action-feedback--success {
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
  color: var(--color-success);
}

@media (max-width: 720px) {
  .settings-action-form {
    grid-template-columns: minmax(0, 1fr);
  }

  .settings-action-controls {
    justify-content: stretch;
  }
}
</style>
