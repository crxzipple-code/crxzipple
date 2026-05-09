<script setup lang="ts">
import {
  CheckCircle2,
  FileJson,
  GitBranch,
  KeyRound,
  Play,
  RefreshCcw,
  Save,
  ShieldAlert,
  Trash2,
  XCircle,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import { useI18n } from "@/shared/i18n";
import UiButton from "@/shared/ui/UiButton.vue";
import {
  createAuthorizationPolicy,
  deleteAuthorizationPolicy,
  dryRunAuthorizationPolicy,
  exportAuthorizationPolicies,
  listAuthorizationAudits,
  listAuthorizationPolicies,
  previewAuthorizationPolicyImpact,
  setAuthorizationPolicyEnabled,
  updateAuthorizationPolicy,
  type AuthorizationAuditApiPayload,
  type AuthorizationCheckRequestPayload,
  type AuthorizationDecisionApiPayload,
  type AuthorizationImpactApiPayload,
  type AuthorizationPolicyApiPayload,
  type AuthorizationPolicyWritePayload,
} from "../api";

const { t } = useI18n();

const policies = ref<AuthorizationPolicyApiPayload[]>([]);
const audits = ref<AuthorizationAuditApiPayload[]>([]);
const selectedPolicyId = ref<string | null>(null);
const isLoading = ref(false);
const actionRunning = ref(false);
const loadError = ref<string | null>(null);
const actionError = ref<string | null>(null);
const notice = ref<string | null>(null);
const searchQuery = ref("");
const editorText = ref("");
const dryRunText = ref(defaultDryRunRequestText());
const resultText = ref("");

const selectedPolicy = computed(() =>
  policies.value.find((policy) => policy.id === selectedPolicyId.value) ?? policies.value[0] ?? null,
);
const filteredPolicies = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  if (!query) return policies.value;
  return policies.value.filter((policy) =>
    [
      policy.id,
      policy.description,
      policy.effect,
      policy.source_kind,
      policy.resource_kind,
      policy.resource_id,
      policy.actions.join(" "),
    ].some((value) => textValue(value).toLowerCase().includes(query)),
  );
});
const enabledCount = computed(() => policies.value.filter((policy) => policy.enabled).length);
const denyCount = computed(() => policies.value.filter((policy) => policy.effect === "deny").length);
const managedCount = computed(() => policies.value.filter((policy) => policy.source_kind === "local_managed").length);
const selectedPolicyAudits = computed(() => {
  if (!selectedPolicy.value) return audits.value.slice(0, 6);
  return audits.value
    .filter((audit) => audit.target_policy_id === selectedPolicy.value?.id || audit.action.startsWith("decision."))
    .slice(0, 6);
});
const selectedPolicySummary = computed(() => {
  const policy = selectedPolicy.value;
  if (!policy) return [];
  return [
    [t("settings.authorization.field.policyId"), policy.id],
    [t("settings.authorization.field.effect"), policy.effect],
    [t("settings.authorization.field.actions"), policy.actions.join(", ") || "-"],
    [t("settings.authorization.field.resource"), `${policy.resource_kind ?? "*"} / ${policy.resource_id ?? "*"}`],
    [t("settings.authorization.field.subject"), `${policy.subject_type ?? "*"} / ${policy.subject_id ?? "*"}`],
    [t("settings.authorization.field.priority"), String(policy.priority)],
    [t("settings.authorization.field.source"), policy.source_kind],
  ];
});

onMounted(() => {
  void loadAuthorizationGovernance();
});

async function loadAuthorizationGovernance(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  actionError.value = null;
  try {
    const [policyPayload, auditPayload] = await Promise.all([
      listAuthorizationPolicies(),
      listAuthorizationAudits({ limit: 30 }),
    ]);
    policies.value = policyPayload;
    audits.value = auditPayload;
    if (!selectedPolicyId.value && policyPayload[0]) {
      selectPolicy(policyPayload[0]);
    } else if (selectedPolicy.value) {
      selectPolicy(selectedPolicy.value);
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    isLoading.value = false;
  }
}

function selectPolicy(policy: AuthorizationPolicyApiPayload): void {
  selectedPolicyId.value = policy.id;
  editorText.value = formatJson(policyToWritePayload(policy));
  resultText.value = "";
  actionError.value = null;
  notice.value = null;
}

async function handleCreatePolicy(): Promise<void> {
  await runPolicyAction(async () => {
    const payload = parsePolicyEditor();
    await createAuthorizationPolicy(withActorAndReason(payload));
    notice.value = t("settings.authorization.notice.created", { id: payload.id });
  });
}

async function handleUpdatePolicy(): Promise<void> {
  await runPolicyAction(async () => {
    const payload = parsePolicyEditor();
    await updateAuthorizationPolicy(payload.id, withActorAndReason(payload));
    notice.value = t("settings.authorization.notice.updated", { id: payload.id });
  });
}

async function handleTogglePolicy(): Promise<void> {
  const policy = selectedPolicy.value;
  if (!policy) return;
  await runPolicyAction(async () => {
    const nextEnabled = !policy.enabled;
    await setAuthorizationPolicyEnabled(
      policy.id,
      nextEnabled,
      `Settings UI ${nextEnabled ? "enable" : "disable"} authorization policy.`,
    );
    notice.value = nextEnabled
      ? t("settings.authorization.notice.enabled", { id: policy.id })
      : t("settings.authorization.notice.disabled", { id: policy.id });
  });
}

async function handleDeletePolicy(): Promise<void> {
  const policy = selectedPolicy.value;
  if (!policy) return;
  await runPolicyAction(async () => {
    await deleteAuthorizationPolicy(policy.id, "Settings UI delete authorization policy.");
    notice.value = t("settings.authorization.notice.deleted", { id: policy.id });
    selectedPolicyId.value = null;
    editorText.value = "";
  });
}

async function handleDryRun(): Promise<void> {
  await runPolicyAction(async () => {
    const request = parseDryRunRequest();
    const decision = await dryRunAuthorizationPolicy(request, "Settings UI dry-run.");
    resultText.value = formatJson(decision);
    notice.value = decision.allowed
      ? t("settings.authorization.notice.allowed")
      : t("settings.authorization.notice.denied");
  }, { keepSelection: true });
}

async function handleImpactPreview(): Promise<void> {
  await runPolicyAction(async () => {
    const request = parseDryRunRequest();
    const policy = parsePolicyEditor();
    const impact = await previewAuthorizationPolicyImpact(
      request,
      [withActorAndReason(policy)],
      "Settings UI impact preview.",
    );
    resultText.value = formatJson(impact);
    notice.value = impact.changed
      ? t("settings.authorization.notice.impactChanged")
      : t("settings.authorization.notice.impactSame");
  }, { keepSelection: true });
}

async function handleExportPolicies(): Promise<void> {
  await runPolicyAction(async () => {
    const exported = await exportAuthorizationPolicies();
    resultText.value = formatJson(exported);
    notice.value = t("settings.authorization.notice.exported", { count: exported.policies.length });
  }, { keepSelection: true });
}

async function runPolicyAction(
  action: () => Promise<void>,
  options: { keepSelection?: boolean } = {},
): Promise<void> {
  actionRunning.value = true;
  actionError.value = null;
  notice.value = null;
  try {
    await action();
    if (options.keepSelection && selectedPolicy.value) {
      audits.value = await listAuthorizationAudits({ limit: 30 });
    } else {
      await loadAuthorizationGovernance();
    }
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionRunning.value = false;
  }
}

function parsePolicyEditor(): AuthorizationPolicyWritePayload {
  const value = parseJsonObject(editorText.value, t("settings.authorization.editor.policyJson"));
  const actions = Array.isArray(value.actions) ? value.actions.map((item) => String(item)) : [];
  const id = textValue(value.id);
  if (!id) throw new Error(t("settings.authorization.error.missingPolicyId"));
  if (!actions.length) throw new Error(t("settings.authorization.error.missingActions"));
  return {
    id,
    description: textValue(value.description),
    effect: textValue(value.effect, "deny"),
    actions,
    subject_type: nullableText(value.subject_type),
    subject_id: nullableText(value.subject_id),
    subject_match: objectValue(value.subject_match),
    resource_kind: nullableText(value.resource_kind),
    resource_id: nullableText(value.resource_id),
    resource_match: objectValue(value.resource_match),
    context_match: objectValue(value.context_match),
    condition: value.condition && typeof value.condition === "object" && !Array.isArray(value.condition)
      ? { ...(value.condition as Record<string, unknown>) }
      : null,
    obligations: Array.isArray(value.obligations)
      ? value.obligations
          .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null && !Array.isArray(item))
          .map((item) => ({ name: textValue(item.name), params: objectValue(item.params) }))
          .filter((item) => item.name)
      : [],
    priority: Number.isFinite(Number(value.priority)) ? Number(value.priority) : 0,
    enabled: typeof value.enabled === "boolean" ? value.enabled : true,
    source_kind: textValue(value.source_kind, "local_managed"),
  };
}

function parseDryRunRequest(): AuthorizationCheckRequestPayload {
  const value = parseJsonObject(dryRunText.value, t("settings.authorization.editor.requestJson"));
  if (!textValue(value.action)) throw new Error(t("settings.authorization.error.missingAction"));
  if (!value.resource || typeof value.resource !== "object" || Array.isArray(value.resource)) {
    throw new Error(t("settings.authorization.error.missingResource"));
  }
  const resource = value.resource as Record<string, unknown>;
  if (!textValue(resource.kind)) throw new Error(t("settings.authorization.error.missingResource"));
  return {
    subject: {
      type: textValue((value.subject as Record<string, unknown> | undefined)?.type, "anonymous"),
      id: nullableText((value.subject as Record<string, unknown> | undefined)?.id),
      attrs: objectValue((value.subject as Record<string, unknown> | undefined)?.attrs),
    },
    action: textValue(value.action),
    resource: {
      kind: textValue(resource.kind),
      id: nullableText(resource.id),
      attrs: objectValue(resource.attrs),
    },
    context: {
      attrs: objectValue((value.context as Record<string, unknown> | undefined)?.attrs),
    },
  };
}

function withActorAndReason(payload: AuthorizationPolicyWritePayload): AuthorizationPolicyWritePayload {
  return {
    ...payload,
    actor: { type: "settings-ui", id: "operator" },
    reason: "Settings UI authorization governance action.",
  };
}

function policyToWritePayload(policy: AuthorizationPolicyApiPayload): AuthorizationPolicyWritePayload {
  return {
    id: policy.id,
    description: policy.description,
    effect: policy.effect,
    actions: policy.actions,
    subject_type: policy.subject_type,
    subject_id: policy.subject_id,
    subject_match: policy.subject_match,
    resource_kind: policy.resource_kind,
    resource_id: policy.resource_id,
    resource_match: policy.resource_match,
    context_match: policy.context_match,
    condition: policy.condition,
    obligations: policy.obligations,
    priority: policy.priority,
    enabled: policy.enabled,
    source_kind: policy.source_kind,
  };
}

function parseJsonObject(raw: string, label: string): Record<string, unknown> {
  try {
    const value = JSON.parse(raw) as unknown;
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(`${label} must be a JSON object.`);
    }
    return value as Record<string, unknown>;
  } catch (error) {
    if (error instanceof Error) throw error;
    throw new Error(String(error));
  }
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? { ...(value as Record<string, unknown>) }
    : {};
}

function nullableText(value: unknown): string | null {
  const text = textValue(value);
  return text || null;
}

function textValue(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function policyStatus(policy: AuthorizationPolicyApiPayload): string {
  return policy.enabled ? t("settings.action.enable") : t("settings.action.disable");
}

function decisionTone(decision: AuthorizationDecisionApiPayload | AuthorizationImpactApiPayload | null): string {
  if (!decision) return "neutral";
  if ("allowed" in decision) return decision.allowed ? "success" : "danger";
  return decision.changed ? "warning" : "success";
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function defaultDryRunRequestText(): string {
  return formatJson({
    subject: { type: "interface", id: "settings-ui", attrs: {} },
    action: "tool.run",
    resource: { kind: "tool", id: "echo", attrs: { mutates_state: false } },
    context: { attrs: { interface: "http" } },
  });
}
</script>

<template>
  <main class="settings-module authorization-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>{{ t("settings.resource.authorizationPolicies") }}</h1>
        <p>{{ t("settings.authorization.pageDescription") }}</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" :disabled="isLoading || actionRunning" @click="loadAuthorizationGovernance">
          <RefreshCcw :size="14" /> {{ t("common.refresh") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="actionRunning" @click="handleExportPolicies">
          <FileJson :size="14" /> {{ t("common.export") }}
        </UiButton>
      </div>
    </header>

    <section class="settings-metric-strip authorization-metrics" style="--metric-count: 5">
      <article class="settings-metric">
        <span><KeyRound :size="15" />{{ t("settings.authorization.metric.policies") }}</span>
        <strong>{{ policies.length }}</strong>
        <small>{{ t("settings.authorization.source.authorizationApi") }}</small>
      </article>
      <article class="settings-metric">
        <span><CheckCircle2 :size="15" />{{ t("settings.authorization.metric.enabled") }}</span>
        <strong>{{ enabledCount }}</strong>
        <small>{{ t("settings.authorization.metric.enabledHint") }}</small>
      </article>
      <article class="settings-metric">
        <span><ShieldAlert :size="15" />{{ t("settings.authorization.metric.deny") }}</span>
        <strong>{{ denyCount }}</strong>
        <small>{{ t("settings.authorization.metric.denyHint") }}</small>
      </article>
      <article class="settings-metric">
        <span><GitBranch :size="15" />{{ t("settings.authorization.metric.managed") }}</span>
        <strong>{{ managedCount }}</strong>
        <small>{{ t("settings.authorization.metric.managedHint") }}</small>
      </article>
      <article class="settings-metric">
        <span><Save :size="15" />{{ t("settings.authorization.metric.audit") }}</span>
        <strong>{{ audits.length }}</strong>
        <small>{{ t("settings.authorization.source.authorizationAudit") }}</small>
      </article>
    </section>

    <section v-if="loadError || actionError || notice" class="authorization-message">
      <span v-if="loadError || actionError" class="danger">{{ loadError || actionError }}</span>
      <span v-else>{{ notice }}</span>
    </section>

    <section class="authorization-layout">
      <article class="settings-panel authorization-table-panel">
        <header class="authorization-panel-header">
          <div>
            <h2>{{ t("settings.authorization.policyTable") }}</h2>
            <p>{{ t("settings.authorization.policyTableHint") }}</p>
          </div>
          <label>
            <input v-model="searchQuery" :placeholder="t('common.search')" />
          </label>
        </header>

        <div class="authorization-table">
          <div class="authorization-row authorization-row--head">
            <span>{{ t("settings.authorization.field.policyId") }}</span>
            <span>{{ t("settings.authorization.field.effect") }}</span>
            <span>{{ t("settings.authorization.field.actions") }}</span>
            <span>{{ t("settings.authorization.field.resource") }}</span>
            <span>{{ t("table.status") }}</span>
          </div>
          <button
            v-for="policy in filteredPolicies"
            :key="policy.id"
            :class="{ active: policy.id === selectedPolicy?.id }"
            class="authorization-row"
            type="button"
            @click="selectPolicy(policy)"
          >
            <span><strong>{{ policy.id }}</strong><small>{{ policy.description || "-" }}</small></span>
            <span :class="['pill', policy.effect === 'deny' ? 'danger' : 'success']">{{ policy.effect }}</span>
            <span>{{ policy.actions.join(", ") }}</span>
            <span>{{ policy.resource_kind ?? "*" }} / {{ policy.resource_id ?? "*" }}</span>
            <span :class="['pill', policy.enabled ? 'success' : 'neutral']">{{ policyStatus(policy) }}</span>
          </button>
          <div v-if="isLoading && !policies.length" class="authorization-empty">{{ t("common.loading") }}...</div>
          <div v-else-if="!filteredPolicies.length" class="authorization-empty">{{ t("settings.authorization.empty.noPolicies") }}</div>
        </div>
      </article>

      <aside class="settings-panel authorization-side-panel">
        <header class="authorization-panel-header">
          <div>
            <h2>{{ t("table.details") }}</h2>
            <p>{{ selectedPolicy?.id ?? t("settings.authorization.empty.noSelection") }}</p>
          </div>
        </header>
        <dl v-if="selectedPolicy" class="authorization-kv">
          <div v-for="[label, value] in selectedPolicySummary" :key="label">
            <dt>{{ label }}</dt>
            <dd>{{ value }}</dd>
          </div>
        </dl>
        <div class="authorization-actions">
          <UiButton size="sm" variant="secondary" :disabled="!selectedPolicy || actionRunning" @click="handleTogglePolicy">
            <XCircle v-if="selectedPolicy?.enabled" :size="14" />
            <CheckCircle2 v-else :size="14" />
            {{ selectedPolicy?.enabled ? t("settings.action.disable") : t("settings.action.enable") }}
          </UiButton>
          <UiButton size="sm" variant="danger" :disabled="!selectedPolicy || actionRunning" @click="handleDeletePolicy">
            <Trash2 :size="14" /> {{ t("settings.authorization.action.delete") }}
          </UiButton>
        </div>
        <section class="authorization-audits">
          <h3>{{ t("settings.authorization.auditTrail") }}</h3>
          <p v-if="!selectedPolicyAudits.length">{{ t("table.noRecords") }}</p>
          <ol v-else>
            <li v-for="audit in selectedPolicyAudits" :key="audit.id">
              <strong>{{ audit.action }}</strong>
              <span>{{ formatTime(audit.created_at) }}</span>
            </li>
          </ol>
        </section>
      </aside>
    </section>

    <section class="authorization-workbench">
      <article class="settings-panel authorization-editor-panel">
        <header class="authorization-panel-header">
          <div>
            <h2>{{ t("settings.authorization.editor.policyJson") }}</h2>
            <p>{{ t("settings.authorization.editor.policyHint") }}</p>
          </div>
          <div class="authorization-toolbar">
            <UiButton size="sm" variant="secondary" :disabled="actionRunning" @click="handleCreatePolicy">{{ t("settings.authorization.action.create") }}</UiButton>
            <UiButton size="sm" variant="primary" :disabled="actionRunning" @click="handleUpdatePolicy">{{ t("settings.authorization.action.update") }}</UiButton>
          </div>
        </header>
        <textarea v-model="editorText" spellcheck="false" />
      </article>

      <article class="settings-panel authorization-evaluator-panel">
        <header class="authorization-panel-header">
          <div>
            <h2>{{ t("settings.authorization.editor.requestJson") }}</h2>
            <p>{{ t("settings.authorization.editor.requestHint") }}</p>
          </div>
          <div class="authorization-toolbar">
            <UiButton size="sm" variant="secondary" :disabled="actionRunning" @click="handleDryRun">
              <Play :size="14" />{{ t("settings.action.dryRun") }}
            </UiButton>
            <UiButton size="sm" variant="secondary" :disabled="actionRunning" @click="handleImpactPreview">
              {{ t("settings.authorization.action.impact") }}
            </UiButton>
          </div>
        </header>
        <div class="authorization-evaluator-grid">
          <textarea v-model="dryRunText" spellcheck="false" />
          <pre :class="['authorization-result', decisionTone(null)]">{{ resultText || t("settings.authorization.empty.noResult") }}</pre>
        </div>
      </article>
    </section>

    <footer class="settings-footer">
      <span><KeyRound :size="14" />{{ t("settings.authorization.source.authorizationApi") }}</span>
      <span><Save :size="14" />{{ t("settings.authorization.source.authorizationAudit") }}</span>
      <span><GitBranch :size="14" />{{ t("settings.authorization.boundary") }}</span>
    </footer>
  </main>
</template>

<style scoped>
.authorization-settings {
  display: grid;
  grid-template-rows: auto auto auto auto;
  gap: 10px;
  min-height: calc(100dvh - var(--shell-topbar-height));
}

.authorization-metrics {
  margin-bottom: 0;
}

.authorization-message {
  display: flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: color-mix(in srgb, var(--surface-panel) 92%, transparent);
  color: var(--color-success);
  font-size: 12px;
}

.authorization-message .danger {
  color: var(--color-danger);
}

.authorization-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 10px;
  min-height: 288px;
}

.authorization-workbench {
  display: grid;
  grid-template-columns: minmax(0, 0.94fr) minmax(0, 1.06fr);
  gap: 10px;
  min-height: 300px;
}

.authorization-table-panel,
.authorization-side-panel,
.authorization-editor-panel,
.authorization-evaluator-panel {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.authorization-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-subtle);
}

.authorization-panel-header h2,
.authorization-panel-header h3,
.authorization-panel-header p {
  margin: 0;
}

.authorization-panel-header h2 {
  font-size: 14px;
}

.authorization-panel-header p {
  margin-top: 3px;
  color: var(--text-muted);
  font-size: 11px;
}

.authorization-panel-header label {
  display: flex;
  align-items: center;
  width: min(300px, 36vw);
}

.authorization-panel-header input {
  width: 100%;
  min-height: 30px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  background: var(--surface-input);
  color: var(--text-primary);
  padding: 0 10px;
}

.authorization-table {
  height: calc(100% - 62px);
  overflow: auto;
}

.authorization-row {
  display: grid;
  grid-template-columns: minmax(210px, 1.25fr) 80px minmax(170px, 1fr) minmax(150px, 0.9fr) 92px;
  gap: 10px;
  align-items: center;
  width: 100%;
  min-height: 46px;
  padding: 0 14px;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}

.authorization-row--head {
  min-height: 38px;
  color: var(--text-muted);
  cursor: default;
  font-size: 11px;
  font-weight: 700;
}

.authorization-row.active {
  background: color-mix(in srgb, var(--color-blue) 10%, transparent);
}

.authorization-row span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.authorization-row strong,
.authorization-row small {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.authorization-row small {
  margin-top: 3px;
  color: var(--text-muted);
  font-size: 11px;
}

.pill {
  display: inline-flex;
  justify-content: center;
  max-width: max-content;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
}

.pill.success {
  background: color-mix(in srgb, var(--color-success) 18%, transparent);
  color: var(--color-success);
}

.pill.danger {
  background: color-mix(in srgb, var(--color-danger) 18%, transparent);
  color: var(--color-danger);
}

.authorization-empty {
  display: grid;
  place-items: center;
  min-height: 140px;
  color: var(--text-muted);
  font-size: 12px;
}

.authorization-kv {
  display: grid;
  gap: 8px;
  padding: 12px 14px;
  margin: 0;
}

.authorization-kv div {
  display: grid;
  grid-template-columns: 98px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.authorization-kv dt {
  color: var(--text-muted);
  font-size: 11px;
}

.authorization-kv dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  text-overflow: ellipsis;
}

.authorization-actions,
.authorization-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.authorization-actions {
  padding: 0 14px 12px;
}

.authorization-audits {
  padding: 12px 14px;
  border-top: 1px solid var(--border-subtle);
}

.authorization-audits h3,
.authorization-audits p,
.authorization-audits ol {
  margin: 0;
}

.authorization-audits h3 {
  font-size: 13px;
}

.authorization-audits p {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 12px;
}

.authorization-audits ol {
  display: grid;
  gap: 7px;
  margin-top: 9px;
  padding: 0;
  list-style: none;
}

.authorization-audits li {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 11px;
}

.authorization-audits span {
  color: var(--text-muted);
}

.authorization-editor-panel textarea,
.authorization-evaluator-panel textarea,
.authorization-result {
  width: 100%;
  height: calc(100% - 65px);
  min-height: 180px;
  margin: 0;
  border: 0;
  border-radius: 0;
  background: color-mix(in srgb, var(--surface-input) 86%, transparent);
  color: var(--text-primary);
  font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  outline: 0;
  padding: 12px 14px;
  resize: none;
}

.authorization-evaluator-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  height: calc(100% - 65px);
}

.authorization-evaluator-grid textarea,
.authorization-result {
  height: 100%;
  min-height: 0;
}

.authorization-result {
  overflow: auto;
  border-left: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  white-space: pre-wrap;
}

@media (max-width: 1100px) {
  .authorization-settings {
    grid-template-rows: auto auto auto auto auto;
  }

  .authorization-layout,
  .authorization-workbench {
    grid-template-columns: 1fr;
  }

  .authorization-side-panel {
    min-height: 260px;
  }
}
</style>
