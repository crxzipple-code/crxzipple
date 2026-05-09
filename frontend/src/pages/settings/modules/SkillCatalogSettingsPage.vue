<script setup lang="ts">
import {
  CheckCircle2,
  FileText,
  GitBranch,
  Package,
  Power,
  RefreshCcw,
  Search,
  Shield,
  Trash2,
  Wrench,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import { listSettingsResources } from "../api";
import {
  getSkill,
  installSkill,
  listSkills,
  validateSkill,
  type SkillApiPayload,
  type SkillDetailApiPayload,
  type SkillInstallApiPayload,
  type SkillInstallScopeApiPayload,
} from "../ownerApis/skillCatalog";

type JsonRecord = Record<string, unknown>;
type TableRow = Record<string, string | number | null>;
type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";
type SkillFilter = "all" | "requirements" | "governed";

interface SettingsSourcePayload {
  kind?: string;
  name?: string;
  source_id?: string;
  version?: number | string | null;
  version_id?: string | null;
  applied?: boolean;
  reason?: string | null;
}

interface SettingsResolutionPayload {
  source?: SettingsSourcePayload;
  sources?: SettingsSourcePayload[];
  override_trace?: SettingsSourcePayload[];
  snapshot_id?: string | null;
  resolved_at?: string | null;
  validation?: {
    ok?: boolean;
    errors?: unknown[];
    warnings?: unknown[];
    metadata?: JsonRecord;
  };
}

interface SettingsResourceSummary {
  resource_id: string;
  id?: string;
  display_name?: string;
  status?: string;
  enabled?: boolean;
  source?: string | null;
  version?: number | string | null;
  updated_at?: string | null;
  metadata?: JsonRecord;
  payload?: JsonRecord;
  effective_config?: JsonRecord;
  resolution?: SettingsResolutionPayload & {
    value?: unknown;
  };
}

interface SettingsListPayload {
  total?: number;
  limit?: number;
  offset?: number;
}

interface SettingsKindPayload {
  title?: string;
  description?: string;
  status?: string;
  resources?: SettingsResourceSummary[];
  list?: SettingsListPayload;
}

const skills = ref<SkillApiPayload[]>([]);
const selectedSkillName = ref<string | null>(null);
const selectedSkillDetail = ref<SkillDetailApiPayload | null>(null);
const settingsOverlay = ref<SettingsKindPayload | null>(null);
const surfaceFilter = ref("interactive");
const workspaceDir = ref("");
const skillFilter = ref<SkillFilter>("all");
const validatePath = ref("");
const installSourceDir = ref("");
const installWorkspaceDir = ref("");
const installScope = ref<SkillInstallScopeApiPayload>("workspace");
const validationResult = ref<SkillApiPayload | null>(null);
const installResult = ref<SkillInstallApiPayload | null>(null);
const isLoading = ref(false);
const detailLoading = ref(false);
const actionLoading = ref<"validate" | "install" | null>(null);
const loadError = ref<string | null>(null);
const detailError = ref<string | null>(null);
const actionMessage = ref<string | null>(null);
const actionError = ref<string | null>(null);

const overlayResources = computed(() => settingsOverlay.value?.resources ?? []);
const ownerTotal = computed(() => skills.value.length);
const overlayTotal = computed(() => settingsOverlay.value?.list?.total ?? overlayResources.value.length);
const sourceTotal = computed(() => new Set(skills.value.map((skill) => skill.source)).size);
const governedTotal = computed(() => skills.value.filter((skill) => Boolean(overlayFor(skill))).length);
const requirementTotal = computed(() => skills.value.filter(hasRequirements).length);

const filteredSkills = computed(() => {
  if (skillFilter.value === "requirements") return skills.value.filter(hasRequirements);
  if (skillFilter.value === "governed") return skills.value.filter((skill) => Boolean(overlayFor(skill)));
  return skills.value;
});

const skillRows = computed<TableRow[]>(() =>
  filteredSkills.value.map((skill) => {
    const overlay = overlayFor(skill);
    return {
      Name: skill.name,
      Source: titleize(skill.source),
      Version: textValue(skill.version),
      Surfaces: textValue(skill.requirements.surfaces),
      Tools: requirementSummary(skill),
      Effects: textValue(skill.requirements.required_effects),
      Resources: skill.resources.length,
      Governance: overlay ? overlayLabel(overlay) : "-",
    };
  }),
);

const selectedSkill = computed(() =>
  selectedSkillDetail.value
    ?? skills.value.find((skill) => skill.name === selectedSkillName.value)
    ?? null,
);

const selectedOverlay = computed(() =>
  selectedSkill.value ? overlayFor(selectedSkill.value) : null,
);

const selectedOverlayTone = computed<StatusTone>(() =>
  selectedOverlay.value ? overlayTone(selectedOverlay.value) : "neutral",
);

const selectedStatusTone = computed<StatusTone>(() =>
  selectedOverlay.value && overlayDisabled(selectedOverlay.value) ? "warning" : "success",
);

const selectedRequirementRows = computed<TableRow[]>(() => {
  const requirements = selectedSkill.value?.requirements;
  if (!requirements) return [];
  return [
    { Requirement: "Required Tools", Values: textValue(requirements.required_tools), Count: requirements.required_tools.length },
    { Requirement: "Optional Tools", Values: textValue(requirements.optional_tools), Count: requirements.optional_tools.length },
    { Requirement: "Suggested Tools", Values: textValue(requirements.suggested_tools), Count: requirements.suggested_tools.length },
    { Requirement: "Required Effects", Values: textValue(requirements.required_effects), Count: requirements.required_effects.length },
    { Requirement: "Compatibility Auth", Values: textValue(requirements.compatibility_auth), Count: requirements.compatibility_auth.length },
    { Requirement: "Compatibility Secrets", Values: textValue(requirements.compatibility_secrets), Count: requirements.compatibility_secrets.length },
    {
      Requirement: "Credential Files",
      Values: textValue(requirements.compatibility_credential_files),
      Count: requirements.compatibility_credential_files.length,
    },
    { Requirement: "Setup Hints", Values: textValue(requirements.setup_hints), Count: requirements.setup_hints.length },
  ];
});

const selectedManifestRows = computed<TableRow[]>(() => {
  const skill = selectedSkill.value;
  if (!skill) return [];
  return [
    { Field: "API Version", Value: skill.manifest.api_version },
    { Field: "Kind", Value: skill.manifest.kind },
    { Field: "Instructions Path", Value: skill.manifest.instructions_path },
    { Field: "When To Use", Value: textValue(skill.manifest.when_to_use) },
    { Field: "Tags", Value: textValue(skill.manifest.tags) },
    { Field: "Anti Patterns", Value: textValue(skill.manifest.anti_patterns) },
    { Field: "Setup Hints", Value: textValue(skill.manifest.setup_hints) },
  ];
});

const selectedPackageRows = computed<TableRow[]>(() => {
  const skill = selectedSkill.value;
  if (!skill) return [];
  return [
    { Field: "Name", Value: skill.name },
    { Field: "Source", Value: skill.source },
    { Field: "Root Path", Value: skill.root_path },
    { Field: "Manifest Path", Value: skill.manifest_path },
    { Field: "Instructions Path", Value: skill.instructions_path },
    { Field: "Version", Value: textValue(skill.version) },
    { Field: "Resources", Value: skill.resources.length },
  ];
});

const selectedResourceRows = computed<TableRow[]>(() =>
  (selectedSkill.value?.resources ?? []).slice(0, 10).map((resource) => ({
    Path: resource.path,
    Kind: titleize(resource.kind),
    Size: formatBytes(resource.size_bytes),
  })),
);

const selectedInstructionsPreview = computed(() => {
  const instructions = selectedSkillDetail.value?.instructions?.trim();
  if (!instructions) return "";
  return instructions.length > 1800 ? `${instructions.slice(0, 1800).trimEnd()}...` : instructions;
});

const overlayRows = computed<TableRow[]>(() =>
  overlayResources.value.slice(0, 8).map((resource) => ({
    Resource: settingsResourceId(resource),
    Status: overlayLabel(resource),
    Selector: overlaySelector(resource),
    Source: textValue(resource.source ?? resource.resolution?.source?.name),
    Version: textValue(resource.version),
    "Updated At": formatTime(resource.updated_at),
  })),
);

const selectedOverlayRows = computed<TableRow[]>(() => {
  const overlay = selectedOverlay.value;
  if (!overlay) return [];
  const config = resourceConfig(overlay);
  return [
    { Field: "Resource", Value: settingsResourceId(overlay) },
    { Field: "Status", Value: overlayLabel(overlay) },
    { Field: "Selector", Value: overlaySelector(overlay) },
    { Field: "Enabled", Value: yesNo(config.enabled ?? overlay.enabled) },
    { Field: "Source", Value: textValue(overlay.source ?? overlay.resolution?.source?.name) },
    { Field: "Version", Value: textValue(overlay.version) },
    { Field: "Updated At", Value: formatTime(overlay.updated_at) },
    { Field: "Override Trace", Value: String(overlay.resolution?.override_trace?.length ?? 0) },
  ];
});

const coverageRows = computed<TableRow[]>(() => [
  { Capability: "List available skills", Endpoint: "GET /skills", Status: "wired" },
  { Capability: "Load selected skill details", Endpoint: "GET /skills/{name}?include_instructions=true", Status: "wired" },
  { Capability: "Validate skill package", Endpoint: "POST /skills/validate", Status: "wired" },
  { Capability: "Install skill package", Endpoint: "POST /skills/install", Status: "wired" },
  { Capability: "Enable / disable skill", Endpoint: "not exposed by Skills HTTP", Status: "disabled" },
  { Capability: "Delete installed skill", Endpoint: "not exposed by Skills HTTP", Status: "disabled" },
  { Capability: "Edit manifest or SKILL.md", Endpoint: "not exposed by Skills HTTP", Status: "disabled" },
]);

onMounted(() => {
  void loadSkillCatalog();
});

async function loadSkillCatalog(preferredSkillName = selectedSkillName.value): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    const [ownerSkills, overlay] = await Promise.all([
      listSkills(ownerQueryParams()),
      loadSettingsOverlay(),
    ]);
    skills.value = ownerSkills;
    settingsOverlay.value = overlay;

    const nextSkillName =
      preferredSkillName && ownerSkills.some((skill) => skill.name === preferredSkillName)
        ? preferredSkillName
        : ownerSkills[0]?.name ?? null;
    selectedSkillName.value = nextSkillName;
    await loadSkillDetail(nextSkillName);
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
    skills.value = [];
    settingsOverlay.value = null;
    selectedSkillName.value = null;
    selectedSkillDetail.value = null;
  } finally {
    isLoading.value = false;
  }
}

async function loadSkillDetail(skillName: string | null): Promise<void> {
  selectedSkillDetail.value = null;
  detailError.value = null;
  if (!skillName) return;
  detailLoading.value = true;
  try {
    selectedSkillDetail.value = await getSkill(skillName, {
      ...ownerQueryParams(),
      includeInstructions: true,
    });
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : String(error);
  } finally {
    detailLoading.value = false;
  }
}

async function loadSettingsOverlay(): Promise<SettingsKindPayload | null> {
  try {
    return await listSettingsResources("skill-catalog", { limit: 50, offset: 0 }) as SettingsKindPayload;
  } catch {
    return null;
  }
}

function ownerQueryParams(): { workspaceDir?: string | null; surface?: string | null } {
  return {
    workspaceDir: workspaceDir.value,
    surface: surfaceFilter.value,
  };
}

function selectSkillResource(row: unknown): void {
  const skillName = rowValue(row, "Name");
  if (!skillName || skillName === selectedSkillName.value) return;
  selectedSkillName.value = skillName;
  void loadSkillDetail(skillName);
}

async function validateFromOwner(): Promise<void> {
  const path = validatePath.value.trim();
  actionMessage.value = null;
  actionError.value = null;
  validationResult.value = null;
  if (!path) {
    actionError.value = "Enter a skill package directory to validate.";
    return;
  }

  actionLoading.value = "validate";
  try {
    const result = await validateSkill(path);
    validationResult.value = result;
    if (!installSourceDir.value.trim()) installSourceDir.value = path;
    actionMessage.value = `Validated ${result.name} through POST /skills/validate.`;
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionLoading.value = null;
  }
}

async function installFromOwner(): Promise<void> {
  const sourceDir = installSourceDir.value.trim();
  const workspace = installWorkspaceDir.value.trim();
  actionMessage.value = null;
  actionError.value = null;
  installResult.value = null;
  if (!sourceDir) {
    actionError.value = "Enter a source directory before installing.";
    return;
  }
  if (installScope.value === "workspace" && !workspace) {
    actionError.value = "Workspace installs require a readable workspace_dir.";
    return;
  }

  actionLoading.value = "install";
  try {
    const result = await installSkill({
      source_dir: sourceDir,
      scope: installScope.value,
      workspace_dir: installScope.value === "workspace" ? workspace : null,
    });
    installResult.value = result;
    actionMessage.value = `Installed ${result.skill.name} to ${result.scope} scope through POST /skills/install.`;
    await loadSkillCatalog(result.skill.name);
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : String(error);
  } finally {
    actionLoading.value = null;
  }
}

function overlayFor(skill: SkillApiPayload): SettingsResourceSummary | null {
  for (const resource of overlayResources.value) {
    if (overlayMatchesSkill(resource, skill)) return resource;
  }
  return null;
}

function overlayMatchesSkill(resource: SettingsResourceSummary, skill: SkillApiPayload): boolean {
  const config = resourceConfig(resource);
  const resourceId = settingsResourceId(resource);
  const displayName = textValue(resource.display_name, "");
  const skillId = textValue(config.skill_id, "");
  const pattern = textValue(config.pattern, "");
  const source = textValue(config.source, "");
  const scope = textValue(config.scope, "").toLowerCase();

  if ([resourceId, displayName, skillId].includes(skill.name)) return true;
  if (pattern && wildcardPatternMatches(pattern, skill.name)) return true;
  if (source && source === skill.source && ["source", "package_source", skill.source].includes(scope)) return true;
  return false;
}

function resourceConfig(resource: SettingsResourceSummary): JsonRecord {
  return objectValue(resource.effective_config)
    ?? objectValue(resource.payload)
    ?? objectValue(resource.resolution?.value)
    ?? {};
}

function overlaySelector(resource: SettingsResourceSummary): string {
  const config = resourceConfig(resource);
  return textValue(config.skill_id, textValue(config.pattern, textValue(config.source, settingsResourceId(resource))));
}

function overlayLabel(resource: SettingsResourceSummary): string {
  if (overlayDisabled(resource)) return "Disabled overlay";
  const config = resourceConfig(resource);
  if (config.enabled === true || resource.enabled === true) return "Enabled overlay";
  return titleize(resource.status, "overlay");
}

function overlayDisabled(resource: SettingsResourceSummary): boolean {
  const config = resourceConfig(resource);
  return config.enabled === false || resource.enabled === false;
}

function overlayTone(resource: SettingsResourceSummary): StatusTone {
  if (overlayDisabled(resource)) return "warning";
  return toneForStatus(resource.status ?? resourceConfig(resource).enabled);
}

function settingsResourceId(resource: SettingsResourceSummary): string {
  return textValue(resource.resource_id, textValue(resource.id, "unknown"));
}

function hasRequirements(skill: SkillApiPayload): boolean {
  const requirements = skill.requirements;
  return [
    requirements.required_tools,
    requirements.optional_tools,
    requirements.suggested_tools,
    requirements.required_effects,
    requirements.compatibility_auth,
    requirements.compatibility_secrets,
    requirements.compatibility_credential_files,
    requirements.setup_hints,
  ].some((items) => items.length > 0);
}

function requirementSummary(skill: SkillApiPayload): string {
  const required = skill.requirements.required_tools.length;
  const optional = skill.requirements.optional_tools.length;
  const suggested = skill.requirements.suggested_tools.length;
  const parts = [
    required ? `${required} required` : "",
    optional ? `${optional} optional` : "",
    suggested ? `${suggested} suggested` : "",
  ].filter(Boolean);
  return parts.join(" / ") || "-";
}

function rowValue(row: unknown, key: string): string | null {
  const value = tableCellValue(row, key);
  return typeof value === "string" && value.trim() ? value : null;
}

function tableCellValue(row: unknown, key: string): unknown {
  if (!isRecord(row)) return null;
  const cells = row.cells;
  if (isRecord(cells)) return cells[key];
  return row[key];
}

function objectValue(value: unknown): JsonRecord | null {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as JsonRecord;
  return null;
}

function textValue(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "boolean") return yesNo(value);
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return value.trim() || fallback;
  if (Array.isArray(value)) {
    const items = value.map((item) => textValue(item, "")).filter(Boolean);
    return items.length ? items.join(", ") : fallback;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return fallback;
  }
}

function yesNo(value: unknown): string {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return textValue(value);
}

function titleize(value: unknown, fallback = "-"): string {
  const text = textValue(value, fallback);
  if (text === "-") return text;
  return text
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function toneForStatus(value: unknown): StatusTone {
  const text = textValue(value, "").toLowerCase();
  if (/(failed|invalid|error|blocked|missing)/.test(text)) return "danger";
  if (/(warning|draft|pending|unknown|disabled|overlay)/.test(text)) return "warning";
  if (/(active|ready|valid|success|published|enabled|wired|true)/.test(text)) return "success";
  if (text) return "info";
  return "neutral";
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "-";
  return value.replace("T", " ").replace(/\.\d+/, "").replace("+00:00", " UTC");
}

function wildcardPatternMatches(pattern: string, value: string): boolean {
  const escaped = pattern
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*/g, ".*")
    .replace(/\?/g, ".");
  return new RegExp(`^${escaped}$`).test(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
</script>

<template>
  <main class="settings-module skill-settings scroll-area">
    <header class="settings-page-header">
      <div>
        <h1>Skill Catalog</h1>
        <p>Owner view from <code>/skills</code>. Settings contributes read-only governance overlay only.</p>
      </div>
      <div class="settings-header-actions">
        <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="loadSkillCatalog()">
          <RefreshCcw :size="14" /> Refresh
        </UiButton>
      </div>
    </header>

    <section v-if="actionMessage || actionError" class="settings-panel skill-notice">
      <p v-if="actionError" class="settings-state--error">{{ actionError }}</p>
      <p v-else>{{ actionMessage }}</p>
    </section>

    <section class="skill-summary-grid">
      <article class="settings-panel skill-summary-card">
        <span><Package :size="18" /></span>
        <div><small>Owner Skills</small><strong>{{ ownerTotal }}</strong><p>Loaded from GET /skills.</p></div>
      </article>
      <article class="settings-panel skill-summary-card">
        <span><GitBranch :size="18" /></span>
        <div><small>Sources</small><strong>{{ sourceTotal }}</strong><p>Filesystem-backed package roots.</p></div>
      </article>
      <article class="settings-panel skill-summary-card">
        <span><Wrench :size="18" /></span>
        <div><small>With Requirements</small><strong>{{ requirementTotal }}</strong><p>Tools, effects, auth, or setup hints.</p></div>
      </article>
      <article class="settings-panel skill-summary-card">
        <span><Shield :size="18" /></span>
        <div><small>Governance Overlay</small><strong>{{ overlayTotal }}</strong><p>Read-only Settings status.</p></div>
      </article>
    </section>

    <section class="skill-query-row">
      <label>
        <span>Surface</span>
        <input v-model="surfaceFilter" placeholder="interactive" />
      </label>
      <label>
        <span>Workspace Dir</span>
        <input v-model="workspaceDir" placeholder="/path/to/workspace" />
      </label>
      <UiButton size="sm" variant="secondary" :disabled="isLoading" @click="loadSkillCatalog()">
        <Search :size="14" /> Apply
      </UiButton>
    </section>

    <section class="skill-tabs-row">
      <nav class="settings-tabs">
        <button :class="{ active: skillFilter === 'all' }" type="button" @click="skillFilter = 'all'">All Skills</button>
        <button :class="{ active: skillFilter === 'requirements' }" type="button" @click="skillFilter = 'requirements'">Requirements ({{ requirementTotal }})</button>
        <button :class="{ active: skillFilter === 'governed' }" type="button" @click="skillFilter = 'governed'">Governed ({{ governedTotal }})</button>
      </nav>
      <span><StatusDot tone="info" />Settings action proxy is not used for Skill writes.</span>
    </section>

    <section class="settings-panel skill-list">
      <div v-if="isLoading" class="settings-state">Loading owner skill catalog...</div>
      <div v-else-if="loadError" class="settings-state settings-state--error">{{ loadError }}</div>
      <div v-else-if="!skills.length" class="settings-state">GET /skills returned no skills for this surface and workspace.</div>
      <DataTable
        v-else
        :columns="['Name', 'Source', 'Version', 'Surfaces', 'Tools', 'Effects', 'Resources', 'Governance']"
        :rows="skillRows"
        section-id="skill-catalog"
        clickable-rows
        @row-click="selectSkillResource"
      />
      <footer>Showing {{ skillRows.length }} loaded rows from {{ ownerTotal }} owner skills.</footer>
    </section>

    <section v-if="selectedSkill || detailLoading || detailError" class="skill-detail-layout">
      <article class="settings-panel skill-detail">
        <template v-if="selectedSkill">
          <header>
            <div>
              <h2>
                <Package :size="18" />{{ selectedSkill.name }}
                <span><StatusDot :tone="selectedStatusTone" />{{ selectedOverlay && overlayDisabled(selectedOverlay) ? "Governance disabled" : "Available" }}</span>
              </h2>
              <p>{{ selectedSkill.description || "No description returned by Skills owner API." }}</p>
            </div>
            <em>{{ titleize(selectedSkill.source) }}</em>
          </header>

          <section class="skill-meta-grid">
            <span><strong>Version</strong>{{ textValue(selectedSkill.version) }}</span>
            <span><strong>Manifest</strong>{{ selectedSkill.manifest_path }}</span>
            <span><strong>Instructions</strong>{{ selectedSkill.instructions_path }}</span>
            <span><strong>Tags</strong>{{ textValue(selectedSkill.tags) }}</span>
          </section>

          <section class="skill-detail-grid">
            <article>
              <div class="settings-panel-heading"><h3>Requirements</h3><span>GET /skills</span></div>
              <DataTable
                v-if="selectedRequirementRows.length"
                :columns="['Requirement', 'Values', 'Count']"
                :rows="selectedRequirementRows"
                section-id="skill-requirements"
                allow-raw-keys
              />
              <div v-else class="settings-state settings-state--compact">No requirements returned.</div>
            </article>
            <article>
              <div class="settings-panel-heading"><h3>Manifest</h3><span>{{ selectedSkill.manifest.kind }}</span></div>
              <DataTable
                :columns="['Field', 'Value']"
                :rows="selectedManifestRows"
                section-id="skill-manifest"
                allow-raw-keys
              />
            </article>
          </section>

          <section class="skill-instructions">
            <div class="settings-panel-heading">
              <h3><FileText :size="14" />Instructions Preview</h3>
              <span>{{ detailLoading ? "loading" : "GET /skills/{name}" }}</span>
            </div>
            <div v-if="detailLoading" class="settings-state settings-state--compact">Loading selected skill instructions...</div>
            <div v-else-if="detailError" class="settings-state settings-state--error settings-state--compact">{{ detailError }}</div>
            <pre v-else-if="selectedInstructionsPreview">{{ selectedInstructionsPreview }}</pre>
            <div v-else class="settings-state settings-state--compact">No instructions returned for the selected skill.</div>
          </section>
        </template>
        <div v-else-if="detailLoading" class="settings-state">Loading selected skill...</div>
        <div v-else class="settings-state settings-state--error">{{ detailError }}</div>
      </article>

      <aside class="skill-side-stack">
        <article class="settings-panel">
          <div class="settings-panel-heading">
            <h2>Governance Overlay</h2>
            <span><StatusDot :tone="selectedOverlayTone" />{{ selectedOverlay ? overlayLabel(selectedOverlay) : "no overlay" }}</span>
          </div>
          <DataTable
            v-if="selectedOverlayRows.length"
            :columns="['Field', 'Value']"
            :rows="selectedOverlayRows"
            section-id="skill-selected-overlay"
            allow-raw-keys
          />
          <div v-else class="settings-state settings-state--compact">No Settings governance overlay matched this skill.</div>
        </article>

        <article class="settings-panel">
          <div class="settings-panel-heading"><h2>Package Paths</h2><span>owner truth</span></div>
          <DataTable
            v-if="selectedPackageRows.length"
            :columns="['Field', 'Value']"
            :rows="selectedPackageRows"
            section-id="skill-package-paths"
            allow-raw-keys
          />
          <div v-else class="settings-state settings-state--compact">Select a skill to inspect package paths.</div>
        </article>

        <article class="settings-panel skill-owner-actions">
          <div class="settings-panel-heading"><h2>Owner Actions</h2><span>/skills</span></div>
          <form class="skill-action-box" @submit.prevent="validateFromOwner">
            <label>
              <span>Validate package path</span>
              <input v-model="validatePath" placeholder="/path/to/skill" />
            </label>
            <UiButton size="sm" variant="secondary" :disabled="actionLoading === 'validate'" type="submit">
              <CheckCircle2 :size="14" /> Validate
            </UiButton>
          </form>
          <form class="skill-action-box" @submit.prevent="installFromOwner">
            <label>
              <span>Install source dir</span>
              <input v-model="installSourceDir" placeholder="/path/to/skill" />
            </label>
            <label>
              <span>Scope</span>
              <select v-model="installScope">
                <option value="workspace">workspace</option>
                <option value="global">global</option>
              </select>
            </label>
            <label>
              <span>Workspace dir</span>
              <input v-model="installWorkspaceDir" :disabled="installScope !== 'workspace'" placeholder="/path/to/workspace" />
            </label>
            <UiButton size="sm" variant="secondary" :disabled="actionLoading === 'install'" type="submit">
              <Package :size="14" /> Install
            </UiButton>
          </form>
          <dl v-if="validationResult || installResult" class="settings-kv skill-action-result">
            <div v-if="validationResult"><dt>Validated</dt><dd>{{ validationResult.name }} from {{ validationResult.root_path }}</dd></div>
            <div v-if="installResult"><dt>Installed</dt><dd>{{ installResult.target_path }}</dd></div>
          </dl>
        </article>

        <article class="settings-panel skill-owner-actions">
          <div class="settings-panel-heading"><h2>Unsupported Mutations</h2><span>Skills API gaps</span></div>
          <p>Enable, disable, delete, and manifest editing are disabled because Skills HTTP does not expose owner endpoints for them.</p>
          <div class="skill-disabled-actions">
            <button type="button" disabled><Power :size="14" /><span>Enable / Disable<small>No Skills owner endpoint</small></span></button>
            <button type="button" disabled><Trash2 :size="14" /><span>Delete Skill<small>No Skills owner endpoint</small></span></button>
            <button type="button" disabled><FileText :size="14" /><span>Edit Manifest<small>No Skills owner endpoint</small></span></button>
          </div>
        </article>
      </aside>
    </section>

    <section class="skill-support-grid">
      <article class="settings-panel">
        <div class="settings-panel-heading"><h3>Resources</h3><span>{{ selectedResourceRows.length }}</span></div>
        <DataTable
          v-if="selectedResourceRows.length"
          :columns="['Path', 'Kind', 'Size']"
          :rows="selectedResourceRows"
          section-id="skill-resources"
          allow-raw-keys
        />
        <div v-else class="settings-state settings-state--compact">No resources returned for the selected skill.</div>
      </article>
      <article class="settings-panel">
        <div class="settings-panel-heading"><h3>Settings Overlay</h3><span>{{ overlayRows.length }}</span></div>
        <DataTable
          v-if="overlayRows.length"
          :columns="['Resource', 'Status', 'Selector', 'Source', 'Version', 'Updated At']"
          :rows="overlayRows"
          section-id="skill-overlay"
          allow-raw-keys
        />
        <div v-else class="settings-state settings-state--compact">No Settings governance overlay returned.</div>
      </article>
      <article class="settings-panel coverage-panel">
        <div class="settings-panel-heading"><h3><CheckCircle2 :size="14" />Endpoint Coverage</h3><span>owner API</span></div>
        <DataTable
          :columns="['Capability', 'Endpoint', 'Status']"
          :rows="coverageRows"
          section-id="skill-endpoint-coverage"
          allow-raw-keys
        />
      </article>
    </section>

    <footer class="settings-footer">
      <span><Package :size="14" />Owner Source: /skills</span>
      <span><Shield :size="14" />Overlay: /ui/settings/skill-catalog</span>
      <span><GitBranch :size="14" />Writes use Skills owner endpoints only.</span>
    </footer>
  </main>
</template>

<style scoped>
.skill-notice {
  min-height: 42px;
  margin-bottom: 10px;
  padding: 11px 14px;
  color: var(--text-secondary);
  font-size: 12px;
}

.skill-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.skill-summary-card {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  min-height: 104px;
}

.skill-summary-card > span {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid color-mix(in srgb, var(--color-accent) 34%, transparent);
  border-radius: var(--radius-2);
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
}

.skill-summary-card div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.skill-summary-card small {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.skill-summary-card strong {
  color: var(--text-primary);
  font-size: 24px;
}

.skill-summary-card p {
  color: var(--text-secondary);
  font-size: 11px;
}

.skill-query-row {
  display: grid;
  grid-template-columns: minmax(160px, 220px) minmax(260px, 1fr) auto;
  gap: 10px;
  align-items: end;
  margin-bottom: 10px;
}

.skill-query-row label,
.skill-action-box label {
  display: grid;
  gap: 5px;
  min-width: 0;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
}

.skill-query-row input,
.skill-action-box input,
.skill-action-box select {
  min-width: 0;
  min-height: 34px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  padding: 0 10px;
  background: var(--surface-raised);
  color: var(--text-primary);
  font: inherit;
}

.skill-query-row input:disabled,
.skill-action-box input:disabled,
.skill-action-box select:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.skill-tabs-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 8px;
}

.skill-tabs-row > span {
  display: inline-flex;
  gap: 7px;
  align-items: center;
  color: var(--text-muted);
  font-size: 11px;
}

.skill-list {
  padding: 0;
  overflow: hidden;
}

.skill-list :deep(td:first-child) {
  color: var(--text-primary);
  font-weight: 750;
}

.skill-list footer {
  min-height: 28px;
  padding: 7px 12px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 11px;
}

.skill-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 10px;
  align-items: start;
  margin-top: 10px;
}

.skill-detail {
  display: grid;
  gap: 12px;
}

.skill-detail > header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.skill-detail h2 {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  font-size: 16px;
}

.skill-detail h2 span {
  display: inline-flex;
  gap: 5px;
  align-items: center;
  min-height: 22px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  padding: 2px 7px;
  color: var(--text-secondary);
  font-size: 11px;
}

.skill-detail header p {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.skill-detail header em {
  flex: 0 0 auto;
  border: 1px solid color-mix(in srgb, var(--color-blue) 34%, transparent);
  border-radius: var(--radius-1);
  padding: 4px 8px;
  color: var(--color-blue);
  font-size: 11px;
  font-style: normal;
  font-weight: 750;
}

.skill-meta-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.skill-meta-grid span {
  display: grid;
  gap: 4px;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  padding: 9px;
  background: color-mix(in srgb, var(--surface-panel-soft) 72%, transparent);
  color: var(--text-secondary);
  font-size: 11px;
  overflow-wrap: anywhere;
}

.skill-meta-grid strong {
  color: var(--text-muted);
  font-size: 10px;
  text-transform: uppercase;
}

.skill-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
  gap: 10px;
}

.skill-detail-grid article,
.skill-instructions {
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  padding: 12px;
  background: color-mix(in srgb, var(--surface-panel-soft) 72%, transparent);
}

.skill-instructions pre {
  max-height: 280px;
  margin: 0;
  overflow: auto;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  padding: 10px;
  background: var(--surface-panel);
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.skill-side-stack,
.skill-support-grid {
  display: grid;
  gap: 10px;
}

.skill-owner-actions {
  display: grid;
  gap: 10px;
}

.skill-owner-actions p {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.5;
}

.skill-action-box {
  display: grid;
  gap: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  padding: 10px;
  background: color-mix(in srgb, var(--surface-panel-soft) 72%, transparent);
}

.skill-action-result {
  border-top: 1px solid var(--border-subtle);
  padding-top: 8px;
}

.skill-disabled-actions {
  display: grid;
  gap: 8px;
}

.skill-disabled-actions button {
  display: flex;
  gap: 9px;
  align-items: center;
  min-height: 46px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  padding: 8px 10px;
  background: var(--surface-panel-soft);
  color: var(--text-muted);
  text-align: left;
}

.skill-disabled-actions span {
  display: grid;
  gap: 2px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 750;
}

.skill-disabled-actions small {
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 600;
}

.skill-support-grid {
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1fr) minmax(0, 1.1fr);
  margin-top: 10px;
}

.coverage-panel :deep(td:nth-child(3)) {
  font-weight: 750;
}

@media (max-width: 1180px) {
  .skill-summary-grid,
  .skill-meta-grid,
  .skill-support-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .skill-detail-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 780px) {
  .skill-summary-grid,
  .skill-query-row,
  .skill-detail-grid,
  .skill-meta-grid,
  .skill-support-grid {
    grid-template-columns: 1fr;
  }

  .skill-tabs-row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
