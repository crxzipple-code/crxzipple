<script setup lang="ts">
import {
  CheckCircle2,
  FileText,
  GitBranch,
  Package,
  Plus,
  Save,
  Power,
  RefreshCcw,
  Search,
  Shield,
  Trash2,
  Wrench,
} from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

import { useI18n } from "@/shared/i18n";
import DataTable from "@/shared/ui/DataTable.vue";
import StatusDot from "@/shared/ui/StatusDot.vue";
import UiButton from "@/shared/ui/UiButton.vue";
import {
  applySkillDraft,
  createSkill,
  createSkillSource,
  deleteSkill,
  deleteSkillDraft,
  deleteSkillSource,
  diffSkillDraft,
  disableSkill,
  enableSkill,
  getSkill,
  getSkillDraft,
  getSkillReadiness,
  installSkill,
  listSkillDrafts,
  listSkillInstallations,
  listSkillSources,
  listSkills,
  rejectSkillDraft,
  syncSkills,
  updateSkill,
  updateSkillSource,
  validateSkillDraft,
  validateSkill,
  writeSkillInstructions,
  type SkillApiPayload,
  type SkillDetailApiPayload,
  type SkillDraftApiPayload,
  type SkillInstallApiPayload,
  type SkillInstallScopeApiPayload,
  type SkillInstallationApiPayload,
  type SkillReadinessApiPayload,
  type SkillSourceApiPayload,
} from "../ownerApis/skillCatalog";

type TableRow = Record<string, string | number | null>;
type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";
type SkillFilter = "all" | "requirements" | "notReady";
type ActionName =
  | "validate"
  | "install"
  | "enable"
  | "disable"
  | "delete"
  | "sync"
  | "readiness"
  | "create"
  | "update"
  | "writeInstructions"
  | "createSource"
  | "updateSource"
  | "deleteSource"
  | "draftValidate"
  | "draftDiff"
  | "draftApply"
  | "draftReject"
  | "draftDelete";
type EditorMode = "create" | "edit";

const { t } = useI18n();

const skills = ref<SkillApiPayload[]>([]);
const sources = ref<SkillSourceApiPayload[]>([]);
const drafts = ref<SkillDraftApiPayload[]>([]);
const selectedSkillName = ref<string | null>(null);
const selectedSkillDetail = ref<SkillDetailApiPayload | null>(null);
const selectedReadiness = ref<SkillReadinessApiPayload | null>(null);
const selectedAuditRows = ref<SkillInstallationApiPayload[]>([]);
const selectedDraftId = ref<string | null>(null);
const selectedDraftDetail = ref<SkillDraftApiPayload | null>(null);
const surfaceFilter = ref("interactive");
const workspaceDir = ref("");
const sourceIdFilter = ref("");
const skillSearch = ref("");
const skillFilter = ref<SkillFilter>("all");
const sourceDialogOpen = ref(false);
const validateDialogOpen = ref(false);
const installDialogOpen = ref(false);
const editorMode = ref<EditorMode>("edit");
const skillForm = ref({
  name: "",
  description: "",
  version: "",
  tags: "",
  requiredTools: "",
  optionalTools: "",
  suggestedTools: "",
  requiredEffects: "",
  requiredAccess: "",
  surfaces: "interactive",
  supportedPlatforms: "",
  setupHints: "",
  instructions: "",
  scope: "workspace" as SkillInstallScopeApiPayload,
  workspaceDir: "",
});
const sourceForm = ref({
  sourceId: "",
  rootPath: "",
  sourceKind: "external" as "managed" | "external",
  enabled: true,
  readonly: false,
  priority: 100,
});
const validatePath = ref("");
const installSourceDir = ref("");
const installWorkspaceDir = ref("");
const installScope = ref<SkillInstallScopeApiPayload>("workspace");
const actionReason = ref("");
const validationResult = ref<SkillApiPayload | null>(null);
const installResult = ref<SkillInstallApiPayload | null>(null);
const isLoading = ref(false);
const detailLoading = ref(false);
const draftsLoading = ref(false);
const draftDetailLoading = ref(false);
const actionLoading = ref<ActionName | null>(null);
const loadError = ref<string | null>(null);
const sourceError = ref<string | null>(null);
const detailError = ref<string | null>(null);
const readinessError = ref<string | null>(null);
const draftsError = ref<string | null>(null);
const draftDetailError = ref<string | null>(null);
const actionMessage = ref<string | null>(null);
const actionError = ref<string | null>(null);

const skillNameColumn = computed(() => t("settings.skill.table.skill"));
const sourceColumn = computed(() => t("settings.skill.table.source"));
const enabledColumn = computed(() => t("settings.skill.table.enabled"));
const readyColumn = computed(() => t("settings.skill.table.ready"));
const surfaceColumn = computed(() => t("settings.skill.table.surface"));
const toolsColumn = computed(() => t("settings.skill.table.tools"));
const accessColumn = computed(() => t("settings.skill.table.access"));
const updatedColumn = computed(() => t("settings.skill.table.updated"));
const fieldColumn = computed(() => t("settings.skill.table.field"));
const valueColumn = computed(() => t("settings.skill.table.value"));
const countColumn = computed(() => t("settings.skill.table.count"));
const pathColumn = computed(() => t("settings.skill.table.path"));
const kindColumn = computed(() => t("settings.skill.table.kind"));
const sizeColumn = computed(() => t("settings.skill.table.size"));
const statusColumn = computed(() => t("settings.skill.table.status"));
const actionColumn = computed(() => t("settings.skill.table.action"));
const messageColumn = computed(() => t("settings.skill.table.message"));
const timeColumn = computed(() => t("settings.skill.table.time"));
const intentColumn = computed(() => t("settings.skill.draft.table.intent"));
const validationColumn = computed(() => t("settings.skill.draft.table.validation"));
const diffColumn = computed(() => t("settings.skill.draft.table.diff"));
const errorsColumn = computed(() => t("settings.skill.draft.table.errors"));
const warningsColumn = computed(() => t("settings.skill.draft.table.warnings"));

const ownerTotal = computed(() => skills.value.length);
const sourceTotal = computed(() => sourceSummaries.value.length);
const enabledTotal = computed(() => skills.value.filter((skill) => skillEnabled(skill) === true).length);
const readyTotal = computed(() => skills.value.filter((skill) => readinessReady(skill) === true).length);
const requirementTotal = computed(() => skills.value.filter(hasRequirements).length);
const notReadyTotal = computed(() => skills.value.filter((skill) => readinessReady(skill) !== true).length);
const activeDraftTotal = computed(() =>
  drafts.value.filter((draft) => !["applied", "rejected", "expired"].includes(draft.status)).length,
);

const filteredSkills = computed(() => {
  const search = skillSearch.value.trim().toLowerCase();
  let items = skills.value;
  if (search) {
    items = items.filter((skill) =>
      [
        skill.name,
        skill.description,
        skill.source,
        skill.source_id,
        ...skill.tags,
      ].some((value) => textValue(value, "").toLowerCase().includes(search)),
    );
  }
  if (skillFilter.value === "requirements") return items.filter(hasRequirements);
  if (skillFilter.value === "notReady") {
    return items.filter((skill) => readinessReady(skill) !== true);
  }
  return items;
});

const skillRows = computed<TableRow[]>(() =>
  filteredSkills.value.map((skill) => ({
    __skillName: skill.name,
    [skillNameColumn.value]: skill.name,
    [sourceColumn.value]: sourceLabel(skill),
    [enabledColumn.value]: enabledLabel(skill),
    [readyColumn.value]: readinessLabel(skill.readiness),
    [surfaceColumn.value]: textValue(skill.requirements.surfaces),
    [toolsColumn.value]: requirementSummary(skill),
    [accessColumn.value]: accessSummary(skill),
    [updatedColumn.value]: formatTime(skill.updated_at),
  })),
);

const skillColumns = computed(() => [
  skillNameColumn.value,
  sourceColumn.value,
  enabledColumn.value,
  readyColumn.value,
  surfaceColumn.value,
  toolsColumn.value,
  accessColumn.value,
  updatedColumn.value,
]);

const selectedSkill = computed(() =>
  selectedSkillDetail.value
    ?? skills.value.find((skill) => skill.name === selectedSkillName.value)
    ?? null,
);

const selectedDraft = computed(() =>
  selectedDraftDetail.value
    ?? drafts.value.find((draft) => draft.draft_id === selectedDraftId.value)
    ?? null,
);

const selectedStatusTone = computed<StatusTone>(() => {
  if (!selectedSkill.value) return "neutral";
  if (skillEnabled(selectedSkill.value) === false) return "warning";
  return readinessTone(selectedSkill.value.readiness ?? selectedReadiness.value);
});

const selectedRequirementRows = computed<TableRow[]>(() => {
  const requirements = selectedSkill.value?.requirements;
  if (!requirements) return [];
  return [
    row(t("settings.skill.requirement.requiredTools"), textValue(requirements.required_tools), requirements.required_tools.length),
    row(t("settings.skill.requirement.optionalTools"), textValue(requirements.optional_tools), requirements.optional_tools.length),
    row(t("settings.skill.requirement.suggestedTools"), textValue(requirements.suggested_tools), requirements.suggested_tools.length),
    row(t("settings.skill.requirement.requiredEffects"), textValue(requirements.required_effects), requirements.required_effects.length),
    row(t("settings.skill.requirement.requiredAccess"), textValue(requirements.required_access), requirements.required_access.length),
    row(t("settings.skill.requirement.supportedPlatforms"), textValue(requirements.supported_platforms), requirements.supported_platforms.length),
    row(t("settings.skill.requirement.setupHints"), textValue(requirements.setup_hints), requirements.setup_hints.length),
  ];
});

const selectedManifestRows = computed<TableRow[]>(() => {
  const skill = selectedSkill.value;
  if (!skill) return [];
  return [
    fieldRow(t("settings.skill.field.apiVersion"), skill.manifest.api_version),
    fieldRow(t("settings.skill.table.kind"), skill.manifest.kind),
    fieldRow(t("settings.skill.field.instructionsPath"), skill.manifest.instructions_path),
    fieldRow(t("settings.skill.field.whenToUse"), textValue(skill.manifest.when_to_use)),
    fieldRow(t("settings.skill.field.tags"), textValue(skill.manifest.tags)),
    fieldRow(t("settings.skill.field.antiPatterns"), textValue(skill.manifest.anti_patterns)),
    fieldRow(t("settings.skill.requirement.setupHints"), textValue(skill.manifest.setup_hints)),
  ];
});

const selectedPackageRows = computed<TableRow[]>(() => {
  const skill = selectedSkill.value;
  if (!skill) return [];
  return [
    fieldRow(t("settings.skill.field.name"), skill.name),
    fieldRow(t("settings.skill.table.source"), sourceLabel(skill)),
    fieldRow(t("settings.skill.field.rootPath"), skill.root_path),
    fieldRow(t("settings.skill.field.manifestPath"), skill.manifest_path),
    fieldRow(t("settings.skill.field.instructionsPath"), skill.instructions_path),
    fieldRow(t("settings.skill.field.version"), textValue(skill.version)),
    fieldRow(t("settings.skill.table.enabled"), enabledLabel(skill)),
    fieldRow(t("settings.skill.table.ready"), readinessLabel(skill.readiness)),
  ];
});

const selectedReadinessRows = computed<TableRow[]>(() => {
  const readiness = selectedReadiness.value ?? selectedSkill.value?.readiness;
  if (!readiness) return [];
  return [
    fieldRow(t("settings.skill.table.status"), readinessLabel(readiness)),
    fieldRow(t("settings.skill.field.missingTools"), textValue(readiness.missing_tools)),
    fieldRow(t("settings.skill.field.missingAccess"), textValue(readiness.missing_access)),
    fieldRow(t("settings.skill.draft.validation.missingEffects"), textValue(readiness.missing_effects)),
    fieldRow(t("settings.skill.draft.validation.unsupportedSurfaces"), textValue(readiness.unsupported_surfaces)),
    fieldRow(t("settings.skill.field.unsupportedPlatform"), textValue(readiness.unsupported_platforms)),
    fieldRow(t("settings.skill.field.validationErrors"), textValue(readiness.validation_errors)),
    fieldRow(t("settings.skill.requirement.setupHints"), textValue(readiness.setup_hints)),
    fieldRow(t("settings.skill.field.checkedAt"), formatTime(readiness.checked_at ?? readiness.updated_at)),
  ];
});

const selectedResourceRows = computed<TableRow[]>(() =>
  (selectedSkill.value?.resources ?? []).slice(0, 12).map((resource) => ({
    [pathColumn.value]: resource.path,
    [kindColumn.value]: titleize(resource.kind),
    [sizeColumn.value]: formatBytes(resource.size_bytes),
  })),
);

const sourceSummaries = computed<SkillSourceApiPayload[]>(() => {
  if (sources.value.length) return sources.value;
  const bySource = new Map<string, SkillSourceApiPayload>();
  for (const skill of skills.value) {
    const sourceId = skill.source_id || skill.source || t("settings.skill.unknownSource");
    const current = bySource.get(sourceId);
    bySource.set(sourceId, {
      source_id: sourceId,
      name: skill.source,
      kind: skill.source,
      status: skill.source_status ?? null,
      enabled: null,
      package_count: (current?.package_count ?? 0) + 1,
    });
  }
  return [...bySource.values()];
});

const sourceRows = computed<TableRow[]>(() =>
  sourceSummaries.value.map((source) => ({
    __sourceId: source.source_id,
    [sourceColumn.value]: source.name || source.source_id,
    [kindColumn.value]: titleize(source.source_kind ?? source.kind ?? source.scope),
    [pathColumn.value]: source.root_path ?? "-",
    [enabledColumn.value]: boolLabel(source.enabled),
    [statusColumn.value]: textValue(source.status),
    [countColumn.value]: source.package_count ?? skills.value.filter((skill) => sourceMatchesSkill(source, skill)).length,
    [updatedColumn.value]: formatTime(source.last_synced_at ?? source.updated_at),
  })),
);

const draftRows = computed<TableRow[]>(() =>
  drafts.value.map((draft) => ({
    __draftId: draft.draft_id,
    [statusColumn.value]: draftStatusLabel(draft),
    [skillNameColumn.value]: draft.skill_name,
    [intentColumn.value]: titleize(draft.intent),
    [validationColumn.value]: draftValidationLabel(draft),
    [diffColumn.value]: draftDiffSummary(draft),
    [errorsColumn.value]: draft.validation?.errors.length ?? 0,
    [warningsColumn.value]: draft.validation?.warnings.length ?? 0,
    [updatedColumn.value]: formatTime(draft.updated_at ?? draft.created_at),
  })),
);

const draftColumns = computed(() => [
  statusColumn.value,
  skillNameColumn.value,
  intentColumn.value,
  validationColumn.value,
  diffColumn.value,
  errorsColumn.value,
  warningsColumn.value,
  updatedColumn.value,
]);

const selectedDraftSummaryRows = computed<TableRow[]>(() => {
  const draft = selectedDraft.value;
  if (!draft) return [];
  return [
    fieldRow(t("settings.skill.draft.field.draftId"), draft.draft_id),
    fieldRow(t("settings.skill.table.status"), draftStatusLabel(draft)),
    fieldRow(t("settings.skill.table.skill"), draft.skill_name),
    fieldRow(t("settings.skill.draft.table.intent"), titleize(draft.intent)),
    fieldRow(t("settings.skill.table.source"), textValue(draft.target_source_id)),
    fieldRow(t("settings.skill.field.scope"), textValue(draft.target_scope)),
    fieldRow(t("settings.skill.field.workspaceDir"), textValue(draft.workspace_dir)),
    fieldRow(t("settings.skill.draft.field.runId"), textValue(draft.created_by_run_id)),
    fieldRow(t("settings.skill.draft.field.actor"), textValue(draft.actor)),
    fieldRow(t("settings.skill.draft.field.expiresAt"), formatTime(draft.expires_at)),
  ];
});

const selectedDraftValidationRows = computed<TableRow[]>(() => {
  const validation = selectedDraft.value?.validation;
  if (!validation) return [];
  return [
    row(t("settings.skill.draft.validation.errors"), textValue(validation.errors), validation.errors.length),
    row(t("settings.skill.draft.validation.warnings"), textValue(validation.warnings), validation.warnings.length),
    row(t("settings.skill.field.missingTools"), textValue(validation.missing_tools), validation.missing_tools.length),
    row(t("settings.skill.field.missingAccess"), textValue(validation.missing_access), validation.missing_access.length),
    row(t("settings.skill.draft.validation.missingEffects"), textValue(validation.missing_effects), validation.missing_effects.length),
    row(t("settings.skill.draft.validation.unsupportedSurfaces"), textValue(validation.unsupported_surfaces), validation.unsupported_surfaces.length),
    row(t("settings.skill.field.unsupportedPlatform"), textValue(validation.unsupported_platforms), validation.unsupported_platforms.length),
    row(t("settings.skill.readiness.title"), textValue(validation.readiness_status), validation.readiness_status ? 1 : 0),
  ];
});

const selectedDraftDiffRows = computed<TableRow[]>(() => {
  const diff = selectedDraft.value?.diff;
  if (!diff) return [];
  const rows = [
    fieldRow(t("settings.skill.draft.diff.summary"), draftDiffSummary(selectedDraft.value as SkillDraftApiPayload)),
    fieldRow(t("settings.skill.manifest.title"), textValue(diff.manifest_diff)),
    fieldRow(t("settings.skill.instructions.title"), textValue(diff.instructions_diff)),
  ];
  for (const fileDiff of diff.file_diffs.slice(0, 8)) {
    rows.push(fieldRow(fileDiff.path, textValue(fileDiff.summary ?? fileDiff.status ?? fileDiff.diff)));
  }
  return rows;
});

const selectedAuditTableRows = computed<TableRow[]>(() =>
  selectedAuditRows.value.map((item) => ({
    [timeColumn.value]: formatTime(item.created_at),
    [actionColumn.value]: titleize(item.action),
    [statusColumn.value]: titleize(item.status),
    [sourceColumn.value]: textValue(item.source_id),
    [messageColumn.value]: textValue(item.message ?? item.reason),
  })),
);

onMounted(() => {
  void loadSkillCatalog();
  void loadSkillDrafts();
});

async function loadSkillCatalog(preferredSkillName = selectedSkillName.value): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  sourceError.value = null;
  try {
    const ownerSkills = await listSkills({
      ...ownerQueryParams(),
      includeDisabled: true,
      includeReadiness: true,
    });
    skills.value = ownerSkills;
    await loadSources();

    const nextSkillName =
      preferredSkillName && ownerSkills.some((skill) => skill.name === preferredSkillName)
        ? preferredSkillName
        : ownerSkills[0]?.name ?? null;
    selectedSkillName.value = nextSkillName;
    await loadSkillDetail(nextSkillName);
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
    skills.value = [];
    sources.value = [];
    selectedSkillName.value = null;
    selectedSkillDetail.value = null;
    selectedReadiness.value = null;
  } finally {
    isLoading.value = false;
  }
}

async function loadSkillDrafts(preferredDraftId = selectedDraftId.value): Promise<void> {
  draftsLoading.value = true;
  draftsError.value = null;
  try {
    const ownerDrafts = await listSkillDrafts({
      workspaceDir: workspaceDir.value,
    });
    drafts.value = ownerDrafts;
    const nextDraftId =
      preferredDraftId && ownerDrafts.some((draft) => draft.draft_id === preferredDraftId)
        ? preferredDraftId
        : ownerDrafts[0]?.draft_id ?? null;
    selectedDraftId.value = nextDraftId;
    await loadSkillDraftDetail(nextDraftId);
  } catch (error) {
    draftsError.value = error instanceof Error ? error.message : String(error);
    drafts.value = [];
    selectedDraftId.value = null;
    selectedDraftDetail.value = null;
  } finally {
    draftsLoading.value = false;
  }
}

async function loadSources(): Promise<void> {
  try {
    sources.value = await listSkillSources(ownerQueryParams());
  } catch (error) {
    sources.value = [];
    sourceError.value = error instanceof Error ? error.message : String(error);
  }
}

async function loadSkillDetail(skillName: string | null): Promise<void> {
  selectedSkillDetail.value = null;
  selectedReadiness.value = null;
  selectedAuditRows.value = [];
  detailError.value = null;
  readinessError.value = null;
  if (!skillName) return;
  detailLoading.value = true;
  try {
    selectedSkillDetail.value = await getSkill(skillName, {
      ...ownerQueryParams(),
      includeInstructions: true,
      includeReadiness: true,
      includeDisabled: true,
    });
    selectedReadiness.value = selectedSkillDetail.value.readiness ?? null;
    populateSkillForm(selectedSkillDetail.value);
    selectedAuditRows.value = await listSkillInstallations({
      skillName,
      limit: 80,
    });
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : String(error);
  } finally {
    detailLoading.value = false;
  }
}

async function loadSkillDraftDetail(draftId: string | null): Promise<void> {
  selectedDraftDetail.value = null;
  draftDetailError.value = null;
  if (!draftId) return;
  draftDetailLoading.value = true;
  try {
    selectedDraftDetail.value = await getSkillDraft(draftId);
  } catch (error) {
    draftDetailError.value = error instanceof Error ? error.message : String(error);
  } finally {
    draftDetailLoading.value = false;
  }
}

function ownerQueryParams(): { workspaceDir?: string | null; surface?: string | null; source?: string | null } {
  return {
    workspaceDir: workspaceDir.value,
    surface: surfaceFilter.value,
    source: sourceIdFilter.value,
  };
}

function selectSkillResource(rowValue: unknown): void {
  const skillName = tableCellValue(rowValue, "__skillName") ?? tableCellValue(rowValue, skillNameColumn.value);
  if (typeof skillName !== "string" || !skillName || skillName === selectedSkillName.value) return;
  editorMode.value = "edit";
  selectedSkillName.value = skillName;
  void loadSkillDetail(skillName);
}

function selectDraftResource(rowValue: unknown): void {
  const draftId = tableCellValue(rowValue, "__draftId") ?? tableCellValue(rowValue, t("settings.skill.draft.field.draftId"));
  if (typeof draftId !== "string" || !draftId || draftId === selectedDraftId.value) return;
  selectedDraftId.value = draftId;
  void loadSkillDraftDetail(draftId);
}

function beginCreateSkill(): void {
  editorMode.value = "create";
  selectedSkillName.value = null;
  selectedSkillDetail.value = null;
  selectedReadiness.value = null;
  selectedAuditRows.value = [];
  skillForm.value = {
    name: "",
    description: "",
    version: "",
    tags: "",
    requiredTools: "",
    optionalTools: "",
    suggestedTools: "",
    requiredEffects: "",
    requiredAccess: "",
    surfaces: surfaceFilter.value || "interactive",
    supportedPlatforms: "",
    setupHints: "",
    instructions: "# New Skill\n\nDescribe how the agent should use this skill.\n",
    scope: "workspace",
    workspaceDir: workspaceDir.value,
  };
}

function populateSkillForm(skill: SkillDetailApiPayload): void {
  editorMode.value = "edit";
  skillForm.value = {
    name: skill.name,
    description: skill.description ?? "",
    version: skill.version ?? "",
    tags: skill.tags.join(", "),
    requiredTools: skill.requirements.required_tools.join(", "),
    optionalTools: skill.requirements.optional_tools.join(", "),
    suggestedTools: skill.requirements.suggested_tools.join(", "),
    requiredEffects: skill.requirements.required_effects.join(", "),
    requiredAccess: skill.requirements.required_access.join(", "),
    surfaces: skill.requirements.surfaces.join(", "),
    supportedPlatforms: skill.requirements.supported_platforms.join(", "),
    setupHints: skill.requirements.setup_hints.join("\n"),
    instructions: skill.instructions ?? "",
    scope: "workspace",
    workspaceDir: workspaceDir.value,
  };
}

async function saveSkillForm(): Promise<void> {
  actionMessage.value = null;
  actionError.value = null;
  const name = skillForm.value.name.trim();
  if (!name) {
    actionError.value = t("settings.skill.error.nameRequired");
    return;
  }
  if (!skillForm.value.description.trim()) {
    actionError.value = t("settings.skill.error.descriptionRequired");
    return;
  }
  if (!skillForm.value.instructions.trim()) {
    actionError.value = t("settings.skill.error.instructionsRequired");
    return;
  }
  if (editorMode.value === "create") {
    await runOwnerAction("create", async () => {
      const result = await createSkill({
        name,
        description: skillForm.value.description.trim(),
        instructions: skillForm.value.instructions,
        scope: skillForm.value.scope,
        workspace_dir: skillForm.value.scope === "workspace" ? skillForm.value.workspaceDir.trim() || workspaceDir.value.trim() || null : null,
        version: skillForm.value.version.trim() || null,
        tags: csvItems(skillForm.value.tags),
        required_tools: csvItems(skillForm.value.requiredTools),
        optional_tools: csvItems(skillForm.value.optionalTools),
        suggested_tools: csvItems(skillForm.value.suggestedTools),
        required_effects: csvItems(skillForm.value.requiredEffects),
        required_access: csvItems(skillForm.value.requiredAccess),
        surfaces: csvItems(skillForm.value.surfaces),
        supported_platforms: csvItems(skillForm.value.supportedPlatforms),
        setup_hints: csvItems(skillForm.value.setupHints),
      });
      actionMessage.value = t("settings.skill.notice.created", { name: result.skill.name });
      await loadSkillCatalog(result.skill.name);
    });
    return;
  }
  if (!selectedSkillName.value) return;
  await runOwnerAction("update", async () => {
    const result = await updateSkill(selectedSkillName.value as string, {
      workspace_dir: workspaceDir.value.trim() || null,
      description: skillForm.value.description.trim(),
      version: skillForm.value.version.trim() || null,
      tags: csvItems(skillForm.value.tags),
      required_tools: csvItems(skillForm.value.requiredTools),
      optional_tools: csvItems(skillForm.value.optionalTools),
      suggested_tools: csvItems(skillForm.value.suggestedTools),
      required_effects: csvItems(skillForm.value.requiredEffects),
      required_access: csvItems(skillForm.value.requiredAccess),
      surfaces: csvItems(skillForm.value.surfaces),
      supported_platforms: csvItems(skillForm.value.supportedPlatforms),
      setup_hints: csvItems(skillForm.value.setupHints),
    });
    actionMessage.value = t("settings.skill.notice.updated", { name: result.skill.name });
    await loadSkillCatalog(result.skill.name);
  });
}

async function saveSkillInstructions(): Promise<void> {
  if (!selectedSkillName.value) return;
  if (!skillForm.value.instructions.trim()) {
    actionError.value = t("settings.skill.error.instructionsRequired");
    return;
  }
  await runOwnerAction("writeInstructions", async () => {
    const result = await writeSkillInstructions(selectedSkillName.value as string, {
      content: skillForm.value.instructions,
      workspace_dir: workspaceDir.value.trim() || null,
    });
    actionMessage.value = t("settings.skill.notice.instructionsSaved", { name: result.skill.name });
    await loadSkillCatalog(result.skill.name);
  });
}

function selectSourceResource(rowValue: unknown): void {
  const sourceId = tableCellValue(rowValue, "__sourceId") ?? tableCellValue(rowValue, sourceColumn.value);
  if (typeof sourceId !== "string" || !sourceId) return;
  const source = sourceSummaries.value.find((item) => item.source_id === sourceId);
  if (source) populateSourceForm(source);
}

function populateSourceForm(source: SkillSourceApiPayload): void {
  sourceForm.value = {
    sourceId: source.source_id,
    rootPath: source.root_path ?? "",
    sourceKind: source.source_kind === "managed" ? "managed" : "external",
    enabled: source.enabled !== false,
    readonly: source.readonly === true,
    priority: Number(source.priority ?? 100),
  };
}

function clearSourceForm(): void {
  sourceForm.value = {
    sourceId: "",
    rootPath: "",
    sourceKind: "external",
    enabled: true,
    readonly: false,
    priority: 100,
  };
}

async function saveSourceFromOwner(): Promise<void> {
  const sourceId = sourceForm.value.sourceId.trim();
  const rootPath = sourceForm.value.rootPath.trim();
  actionMessage.value = null;
  actionError.value = null;
  if (!sourceId || !rootPath) {
    actionError.value = t("settings.skill.error.sourceRequired");
    return;
  }
  const existing = sources.value.some((source) => source.source_id === sourceId);
  await runOwnerAction(existing ? "updateSource" : "createSource", async () => {
    if (existing) {
      const result = await updateSkillSource(sourceId, {
        root_path: rootPath,
        enabled: sourceForm.value.enabled,
        readonly: sourceForm.value.readonly,
        priority: Number(sourceForm.value.priority || 100),
      });
      actionMessage.value = t("settings.skill.notice.sourceUpdated", { id: result.source.source_id });
    } else {
      const result = await createSkillSource({
        source_id: sourceId,
        root_path: rootPath,
        source_kind: sourceForm.value.sourceKind,
        enabled: sourceForm.value.enabled,
        readonly: sourceForm.value.readonly,
        priority: Number(sourceForm.value.priority || 100),
      });
      actionMessage.value = t("settings.skill.notice.sourceCreated", { id: result.source.source_id });
    }
    await loadSkillCatalog(selectedSkillName.value);
  });
}

async function deleteSourceFromOwner(): Promise<void> {
  const sourceId = sourceForm.value.sourceId.trim();
  if (!sourceId) return;
  if (!window.confirm(t("settings.skill.source.deleteConfirm", { id: sourceId }))) return;
  await runOwnerAction("deleteSource", async () => {
    await deleteSkillSource(sourceId);
    actionMessage.value = t("settings.skill.notice.sourceDeleted", { id: sourceId });
    clearSourceForm();
    await loadSkillCatalog(selectedSkillName.value);
  });
}

async function validateFromOwner(): Promise<void> {
  const path = validatePath.value.trim();
  actionMessage.value = null;
  actionError.value = null;
  validationResult.value = null;
  if (!path) {
    actionError.value = t("settings.skill.error.validationPathRequired");
    return;
  }

  await runOwnerAction("validate", async () => {
    const result = await validateSkill(path);
    validationResult.value = result;
    if (!installSourceDir.value.trim()) installSourceDir.value = path;
    actionMessage.value = t("settings.skill.notice.validated", { name: result.name });
  });
}

async function installFromOwner(): Promise<void> {
  const sourceDir = installSourceDir.value.trim();
  const workspace = installWorkspaceDir.value.trim();
  actionMessage.value = null;
  actionError.value = null;
  installResult.value = null;
  if (!sourceDir) {
    actionError.value = t("settings.skill.error.installSourceRequired");
    return;
  }
  if (installScope.value === "workspace" && !workspace) {
    actionError.value = t("settings.skill.error.workspaceRequired");
    return;
  }

  await runOwnerAction("install", async () => {
    const result = await installSkill({
      source_dir: sourceDir,
      scope: installScope.value,
      workspace_dir: installScope.value === "workspace" ? workspace : null,
    });
    installResult.value = result;
    actionMessage.value = t("settings.skill.notice.installed", { name: result.skill.name, scope: result.scope });
    await loadSkillCatalog(result.skill.name);
  });
}

async function syncFromOwner(): Promise<void> {
  await runOwnerAction("sync", async () => {
    await syncSkills(ownerQueryParams());
    actionMessage.value = t("settings.skill.notice.synced");
    await loadSkillCatalog(selectedSkillName.value);
  });
}

async function refreshSelectedReadiness(): Promise<void> {
  if (!selectedSkillName.value) return;
  readinessError.value = null;
  await runOwnerAction("readiness", async () => {
    selectedReadiness.value = await getSkillReadiness(selectedSkillName.value as string, ownerQueryParams());
    actionMessage.value = t("settings.skill.notice.readinessLoaded", { name: selectedSkillName.value as string });
  });
}

async function enableSelectedSkill(): Promise<void> {
  if (!selectedSkillName.value) return;
  await runOwnerAction("enable", async () => {
    await enableSkill(selectedSkillName.value as string, {
      workspace_dir: workspaceDir.value.trim() || null,
      surface: surfaceFilter.value,
      reason: actionReason.value.trim() || null,
    });
    actionMessage.value = t("settings.skill.notice.enabled", { name: selectedSkillName.value as string });
    await loadSkillCatalog(selectedSkillName.value);
  });
}

async function disableSelectedSkill(): Promise<void> {
  if (!selectedSkillName.value) return;
  await runOwnerAction("disable", async () => {
    await disableSkill(selectedSkillName.value as string, {
      workspace_dir: workspaceDir.value.trim() || null,
      surface: surfaceFilter.value,
      reason: actionReason.value.trim() || null,
    });
    actionMessage.value = t("settings.skill.notice.disabled", { name: selectedSkillName.value as string });
    await loadSkillCatalog(selectedSkillName.value);
  });
}

async function deleteSelectedSkill(): Promise<void> {
  if (!selectedSkillName.value) return;
  const deletedName = selectedSkillName.value;
  await runOwnerAction("delete", async () => {
    await deleteSkill(deletedName, ownerQueryParams());
    actionMessage.value = t("settings.skill.notice.deleted", { name: deletedName });
    await loadSkillCatalog(null);
  });
}

async function validateSelectedDraft(): Promise<void> {
  if (!selectedDraftId.value) return;
  const draftId = selectedDraftId.value;
  await runOwnerAction("draftValidate", async () => {
    selectedDraftDetail.value = await validateSkillDraft(draftId);
    actionMessage.value = t("settings.skill.draft.notice.validated", { id: draftId });
    await loadSkillDrafts(draftId);
  });
}

async function diffSelectedDraft(): Promise<void> {
  if (!selectedDraftId.value) return;
  const draftId = selectedDraftId.value;
  await runOwnerAction("draftDiff", async () => {
    selectedDraftDetail.value = await diffSkillDraft(draftId);
    actionMessage.value = t("settings.skill.draft.notice.diffed", { id: draftId });
    await loadSkillDrafts(draftId);
  });
}

async function applySelectedDraft(): Promise<void> {
  if (!selectedDraftId.value) return;
  const draftId = selectedDraftId.value;
  if (!window.confirm(t("settings.skill.draft.applyConfirm", { id: draftId }))) return;
  await runOwnerAction("draftApply", async () => {
    selectedDraftDetail.value = await applySkillDraft(draftId, {
      reason: actionReason.value.trim() || null,
    });
    actionMessage.value = t("settings.skill.draft.notice.applied", { id: draftId });
    await loadSkillDrafts(draftId);
    await loadSkillCatalog(selectedSkillName.value);
  });
}

async function rejectSelectedDraft(): Promise<void> {
  if (!selectedDraftId.value) return;
  const draftId = selectedDraftId.value;
  await runOwnerAction("draftReject", async () => {
    selectedDraftDetail.value = await rejectSkillDraft(draftId, {
      reason: actionReason.value.trim() || null,
    });
    actionMessage.value = t("settings.skill.draft.notice.rejected", { id: draftId });
    await loadSkillDrafts(draftId);
  });
}

async function deleteSelectedDraft(): Promise<void> {
  if (!selectedDraftId.value) return;
  const draftId = selectedDraftId.value;
  if (!window.confirm(t("settings.skill.draft.deleteConfirm", { id: draftId }))) return;
  await runOwnerAction("draftDelete", async () => {
    await deleteSkillDraft(draftId);
    actionMessage.value = t("settings.skill.draft.notice.deleted", { id: draftId });
    await loadSkillDrafts(null);
  });
}

async function runOwnerAction(action: ActionName, callback: () => Promise<void>): Promise<void> {
  actionLoading.value = action;
  actionError.value = null;
  actionMessage.value = null;
  try {
    await callback();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (action === "readiness") readinessError.value = message;
    if (action.startsWith("draft")) draftDetailError.value = message;
    actionError.value = message;
  } finally {
    actionLoading.value = null;
  }
}

function row(label: string, value: string, count: number): TableRow {
  return {
    [fieldColumn.value]: label,
    [valueColumn.value]: value,
    [countColumn.value]: count,
  };
}

function fieldRow(field: string, value: string): TableRow {
  return {
    [fieldColumn.value]: field,
    [valueColumn.value]: value,
  };
}

function sourceMatchesSkill(source: SkillSourceApiPayload, skill: SkillApiPayload): boolean {
  const candidates = [source.source_id, source.name, source.kind, source.source_kind].filter(Boolean);
  return candidates.includes(skill.source_id ?? "") || candidates.includes(skill.source);
}

function sourceLabel(skill: SkillApiPayload): string {
  return textValue(skill.source_id ?? skill.source, t("settings.skill.unknownSource"));
}

function skillEnabled(skill: SkillApiPayload): boolean | null {
  if (typeof skill.enabled === "boolean") return skill.enabled;
  if (typeof skill.enablement?.enabled === "boolean") return skill.enablement.enabled;
  return null;
}

function enabledLabel(skill: SkillApiPayload): string {
  const enabled = skillEnabled(skill);
  if (enabled === true) return t("settings.skill.status.enabled");
  if (enabled === false) return t("settings.skill.status.disabled");
  return t("settings.skill.status.notReported");
}

function boolLabel(value: boolean | null | undefined): string {
  if (value === true) return t("common.yes");
  if (value === false) return t("common.no");
  return t("settings.skill.status.notReported");
}

function readinessReady(skill: SkillApiPayload): boolean | null {
  const readiness = skill.readiness;
  if (!readiness) return null;
  if (typeof readiness.ready === "boolean") return readiness.ready;
  return readiness.status === "ready";
}

function readinessLabel(readiness: SkillReadinessApiPayload | null | undefined): string {
  if (!readiness) return t("settings.skill.status.notReported");
  if (readiness.ready === true || readiness.status === "ready") return t("settings.skill.status.ready");
  if (readiness.ready === false && !readiness.status) return t("settings.skill.status.notReady");
  return titleize(readiness.status, t("settings.skill.status.notReady"));
}

function readinessTone(readiness: SkillReadinessApiPayload | null | undefined): StatusTone {
  if (!readiness) return "warning";
  const status = textValue(readiness.status, "").toLowerCase();
  if (readiness.ready === true || status === "ready") return "success";
  if (/(invalid|unsupported|missing|blocked)/.test(status)) return "danger";
  if (/(setup|disabled|unknown)/.test(status) || readiness.ready === false) return "warning";
  return status ? "info" : "warning";
}

function draftStatusLabel(draft: SkillDraftApiPayload | null | undefined): string {
  return titleize(draft?.status, t("settings.skill.status.notReported"));
}

function draftValidationLabel(draft: SkillDraftApiPayload): string {
  const validation = draft.validation;
  if (!validation) return t("settings.skill.draft.validation.notRun");
  if (validation.errors.length) {
    return t("settings.skill.draft.validation.errorCount", { count: validation.errors.length });
  }
  if (validation.warnings.length) {
    return t("settings.skill.draft.validation.warningCount", { count: validation.warnings.length });
  }
  return t("settings.skill.draft.validation.clean");
}

function draftDiffSummary(draft: SkillDraftApiPayload): string {
  const diff = draft.diff;
  if (!diff) return t("settings.skill.draft.diff.notBuilt");
  const summary = textValue(diff.summary, "");
  if (summary) return summary;
  if (diff.file_diffs.length) {
    return t("settings.skill.draft.diff.fileCount", { count: diff.file_diffs.length });
  }
  return t("settings.skill.draft.diff.ready");
}

function hasRequirements(skill: SkillApiPayload): boolean {
  const requirements = skill.requirements;
  return [
    requirements.required_tools,
    requirements.optional_tools,
    requirements.suggested_tools,
    requirements.required_effects,
    requirements.required_access,
    requirements.supported_platforms,
    requirements.setup_hints,
  ].some((items) => items.length > 0);
}

function requirementSummary(skill: SkillApiPayload): string {
  const required = skill.requirements.required_tools.length;
  const optional = skill.requirements.optional_tools.length;
  const suggested = skill.requirements.suggested_tools.length;
  const parts = [
    required ? t("settings.skill.summary.requiredTools", { count: required }) : "",
    optional ? t("settings.skill.summary.optionalTools", { count: optional }) : "",
    suggested ? t("settings.skill.summary.suggestedTools", { count: suggested }) : "",
  ].filter(Boolean);
  return parts.join(" / ") || "-";
}

function accessSummary(skill: SkillApiPayload): string {
  const access = [
    ...skill.requirements.required_access,
    ...(skill.readiness?.missing_access ?? []),
  ];
  return access.length ? String(new Set(access).size) : "-";
}

function csvItems(value: string): string[] {
  return Array.from(new Set(
    value
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean),
  ));
}

function tableCellValue(row: unknown, key: string): unknown {
  if (!isRecord(row)) return null;
  const cells = row.cells;
  if (isRecord(cells)) return cells[key];
  return row[key];
}

function textValue(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "boolean") return value ? t("common.yes") : t("common.no");
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

function titleize(value: unknown, fallback = "-"): string {
  const text = textValue(value, fallback);
  if (text === "-") return text;
  return text
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
</script>

<template>
  <main class="settings-module skill-settings skill-console scroll-area">
    <header class="skill-console-header">
      <div class="skill-title">
        <h1>{{ t("settings.skill.title") }}</h1>
        <p>{{ t("settings.skill.pageDescription") }}</p>
      </div>
      <div class="skill-header-actions">
        <UiButton size="sm" variant="primary" @click="beginCreateSkill">
          <Plus :size="14" /> {{ t("settings.skill.action.new") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" @click="sourceDialogOpen = true">
          <GitBranch :size="14" /> {{ t("settings.skill.sources.title") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" @click="validateDialogOpen = true">
          <CheckCircle2 :size="14" /> {{ t("settings.action.validate") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" @click="installDialogOpen = true">
          <Wrench :size="14" /> {{ t("settings.skill.action.install") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="actionLoading === 'sync'" @click="syncFromOwner">
          <GitBranch :size="14" /> {{ t("settings.skill.action.sync") }}
        </UiButton>
        <UiButton size="sm" variant="secondary" :disabled="isLoading || draftsLoading" @click="() => { void loadSkillCatalog(); void loadSkillDrafts(); }">
          <RefreshCcw :size="14" /> {{ t("common.refresh") }}
        </UiButton>
      </div>
    </header>

    <section v-if="actionMessage || actionError" class="settings-panel skill-notice">
      <p v-if="actionError" class="settings-state--error">{{ actionError }}</p>
      <p v-else>{{ actionMessage }}</p>
    </section>

    <section class="skill-command-strip">
      <div class="skill-kpi-strip">
        <article class="settings-panel skill-kpi-card">
          <span><Package :size="16" /></span>
          <div><small>{{ t("settings.skill.metric.skills") }}</small><strong>{{ ownerTotal }}</strong></div>
        </article>
        <article class="settings-panel skill-kpi-card">
          <span><GitBranch :size="16" /></span>
          <div><small>{{ t("settings.skill.metric.sources") }}</small><strong>{{ sourceTotal }}</strong></div>
        </article>
        <article class="settings-panel skill-kpi-card">
          <span><Power :size="16" /></span>
          <div><small>{{ t("settings.skill.metric.enabled") }}</small><strong>{{ enabledTotal }}</strong></div>
        </article>
        <article class="settings-panel skill-kpi-card">
          <span><Shield :size="16" /></span>
          <div><small>{{ t("settings.skill.metric.ready") }}</small><strong>{{ readyTotal }}</strong></div>
        </article>
        <article class="settings-panel skill-kpi-card">
          <span><CheckCircle2 :size="16" /></span>
          <div><small>{{ t("settings.skill.tab.notReady") }}</small><strong>{{ notReadyTotal }}</strong></div>
        </article>
        <article class="settings-panel skill-kpi-card">
          <span><FileText :size="16" /></span>
          <div><small>{{ t("settings.skill.draft.metric.active") }}</small><strong>{{ activeDraftTotal }}</strong></div>
        </article>
      </div>

      <div class="settings-panel skill-filter-grid">
        <label class="skill-filter-wide">
          <span>{{ t("common.searchAction") }}</span>
          <input v-model="skillSearch" :placeholder="t('common.search')" />
        </label>
        <label>
          <span>{{ t("settings.skill.field.surface") }}</span>
          <input v-model="surfaceFilter" placeholder="interactive" />
        </label>
        <label class="skill-filter-wide">
          <span>{{ t("settings.skill.field.workspaceDir") }}</span>
          <input v-model="workspaceDir" placeholder="/path/to/workspace" />
        </label>
        <label>
          <span>{{ t("settings.skill.field.sourceId") }}</span>
          <input v-model="sourceIdFilter" placeholder="workspace" />
        </label>
        <UiButton size="sm" variant="secondary" :disabled="isLoading || draftsLoading" @click="() => { void loadSkillCatalog(); void loadSkillDrafts(); }">
          <Search :size="14" /> {{ t("settings.skill.action.apply") }}
        </UiButton>
      </div>
    </section>

    <section class="skill-workbench-grid">
      <article class="settings-panel skill-catalog-panel">
        <div class="skill-panel-head">
          <div>
            <h2>{{ t("settings.skill.metric.skills") }}</h2>
            <p>{{ t("settings.skill.listSummary", { shown: skillRows.length, total: ownerTotal }) }}</p>
          </div>
          <span><StatusDot tone="info" />{{ t("settings.skill.ownerBoundary") }}</span>
        </div>

        <nav class="settings-tabs skill-tabs">
          <button :class="{ active: skillFilter === 'all' }" type="button" @click="skillFilter = 'all'">{{ t("settings.skill.tab.all") }}</button>
          <button :class="{ active: skillFilter === 'requirements' }" type="button" @click="skillFilter = 'requirements'">{{ t("settings.skill.tab.requirements", { count: requirementTotal }) }}</button>
          <button :class="{ active: skillFilter === 'notReady' }" type="button" @click="skillFilter = 'notReady'">{{ t("settings.skill.tab.notReady") }}</button>
        </nav>

        <div class="skill-table-frame">
          <div v-if="isLoading" class="settings-state">{{ t("settings.skill.loading") }}</div>
          <div v-else-if="loadError" class="settings-state settings-state--error">{{ loadError }}</div>
          <div v-else-if="!skills.length" class="settings-state">{{ t("settings.skill.empty.noSkills") }}</div>
          <DataTable
            v-else
            :columns="skillColumns"
            :rows="skillRows"
            section-id="skill-catalog"
            :page-size="8"
            clickable-rows
            @row-click="selectSkillResource"
          />
        </div>

        <section class="skill-draft-queue-section">
          <div class="skill-panel-head skill-panel-head--compact">
            <div>
              <h2><FileText :size="15" />{{ t("settings.skill.draft.queueTitle") }}</h2>
              <p>{{ t("settings.skill.draft.queueDescription") }}</p>
            </div>
            <span><StatusDot tone="info" />/skills/drafts</span>
          </div>
          <div class="skill-draft-queue">
            <div v-if="draftsLoading" class="settings-state settings-state--compact">{{ t("settings.skill.draft.loading") }}</div>
            <div v-else-if="draftsError" class="settings-state settings-state--error settings-state--compact">{{ draftsError }}</div>
            <div v-else-if="!drafts.length" class="settings-state settings-state--compact">{{ t("settings.skill.draft.empty") }}</div>
            <DataTable
              v-else
              :columns="draftColumns"
              :rows="draftRows"
              section-id="skill-drafts"
              allow-raw-keys
              clickable-rows
              :page-size="4"
              @row-click="selectDraftResource"
            />
          </div>
        </section>
      </article>

      <article class="settings-panel skill-editor-panel">
        <template v-if="selectedSkill || editorMode === 'create'">
          <header class="skill-editor-header">
            <div>
              <h2>
                <Package :size="17" />
                {{ editorMode === 'create' ? t("settings.skill.editor.newTitle") : selectedSkill?.name }}
              </h2>
            </div>
            <span v-if="selectedSkill" class="skill-status-pill">
              <StatusDot :tone="selectedStatusTone" />{{ enabledLabel(selectedSkill) }} / {{ readinessLabel(selectedReadiness ?? selectedSkill.readiness) }}
            </span>
          </header>

          <section class="skill-editor-grid">
            <label>
              <span>{{ t("settings.skill.field.name") }}</span>
              <input v-model="skillForm.name" :disabled="editorMode === 'edit'" placeholder="skill-name" />
            </label>
            <label>
              <span>{{ t("settings.skill.field.version") }}</span>
              <input v-model="skillForm.version" placeholder="1.0.0" />
            </label>
            <label>
              <span>{{ t("settings.skill.field.tags") }}</span>
              <input v-model="skillForm.tags" placeholder="support, internal" />
            </label>
            <label>
              <span>{{ t("settings.skill.field.surface") }}</span>
              <input v-model="skillForm.surfaces" placeholder="interactive" />
            </label>
            <label class="skill-editor-wide">
              <span>{{ t("settings.skill.field.description") }}</span>
              <input v-model="skillForm.description" />
            </label>
            <label>
              <span>{{ t("settings.skill.requirement.requiredTools") }}</span>
              <input v-model="skillForm.requiredTools" />
            </label>
            <label>
              <span>{{ t("settings.skill.requirement.requiredAccess") }}</span>
              <input v-model="skillForm.requiredAccess" />
            </label>
            <label>
              <span>{{ t("settings.skill.requirement.requiredEffects") }}</span>
              <input v-model="skillForm.requiredEffects" />
            </label>
            <label>
              <span>{{ t("settings.skill.requirement.optionalTools") }}</span>
              <input v-model="skillForm.optionalTools" />
            </label>
            <label>
              <span>{{ t("settings.skill.requirement.suggestedTools") }}</span>
              <input v-model="skillForm.suggestedTools" />
            </label>
            <label>
              <span>{{ t("settings.skill.requirement.supportedPlatforms") }}</span>
              <input v-model="skillForm.supportedPlatforms" placeholder="darwin, linux" />
            </label>
            <label v-if="editorMode === 'create'">
              <span>{{ t("settings.skill.field.scope") }}</span>
              <select v-model="skillForm.scope">
                <option value="workspace">workspace</option>
                <option value="global">global</option>
              </select>
            </label>
            <label v-if="editorMode === 'create'">
              <span>{{ t("settings.skill.field.workspaceDir") }}</span>
              <input v-model="skillForm.workspaceDir" :disabled="skillForm.scope !== 'workspace'" />
            </label>
            <label class="skill-editor-wide">
              <span>{{ t("settings.skill.requirement.setupHints") }}</span>
              <input v-model="skillForm.setupHints" />
            </label>
          </section>

          <section class="skill-inline-actions">
            <UiButton size="sm" variant="primary" :disabled="actionLoading === 'create' || actionLoading === 'update'" @click="saveSkillForm">
              <Save :size="14" /> {{ editorMode === 'create' ? t("settings.skill.action.create") : t("settings.skill.action.saveMetadata") }}
            </UiButton>
            <UiButton v-if="editorMode === 'edit'" size="sm" variant="secondary" :disabled="actionLoading === 'writeInstructions'" @click="saveSkillInstructions">
              <FileText :size="14" /> {{ t("settings.skill.action.saveInstructions") }}
            </UiButton>
          </section>

          <section class="skill-instructions">
            <div class="settings-panel-heading">
              <h3><FileText :size="14" />{{ t("settings.skill.instructions.editorTitle") }}</h3>
              <span>{{ detailLoading ? t("common.loading") : t("settings.skill.ownerApi") }}</span>
            </div>
            <div v-if="detailLoading" class="settings-state settings-state--compact">{{ t("settings.skill.loadingDetail") }}</div>
            <div v-else-if="detailError" class="settings-state settings-state--error settings-state--compact">{{ detailError }}</div>
            <textarea v-else v-model="skillForm.instructions" :placeholder="t('settings.skill.empty.noInstructions')" />
          </section>
        </template>
        <div v-else-if="detailLoading" class="settings-state">{{ t("settings.skill.loadingDetail") }}</div>
        <div v-else-if="detailError" class="settings-state settings-state--error">{{ detailError }}</div>
        <div v-else class="settings-state">{{ t("settings.skill.empty.noSelection") }}</div>
      </article>

      <aside class="skill-context-stack">
        <article class="settings-panel skill-owner-actions">
          <div class="settings-panel-heading"><h2>{{ t("settings.skill.actions.title") }}</h2><span>/skills</span></div>
          <label>
            <span>{{ t("settings.actionPanel.reason") }}</span>
            <input v-model="actionReason" :placeholder="t('settings.actionPanel.reasonPlaceholder')" />
          </label>
          <div class="skill-action-buttons">
            <UiButton size="sm" variant="secondary" :disabled="!selectedSkill || actionLoading === 'enable'" @click="enableSelectedSkill">
              <Power :size="14" /> {{ t("settings.action.enable") }}
            </UiButton>
            <UiButton size="sm" variant="secondary" :disabled="!selectedSkill || actionLoading === 'disable'" @click="disableSelectedSkill">
              <Power :size="14" /> {{ t("settings.action.disable") }}
            </UiButton>
            <UiButton size="sm" variant="secondary" :disabled="!selectedSkill || actionLoading === 'readiness'" @click="refreshSelectedReadiness">
              <CheckCircle2 :size="14" /> {{ t("settings.skill.action.readiness") }}
            </UiButton>
            <UiButton size="sm" variant="danger" :disabled="!selectedSkill || actionLoading === 'delete'" @click="deleteSelectedSkill">
              <Trash2 :size="14" /> {{ t("settings.skill.action.delete") }}
            </UiButton>
          </div>
        </article>

        <article class="settings-panel skill-draft-review">
          <header>
            <div>
              <h3><FileText :size="15" />{{ selectedDraft?.skill_name ?? t("settings.skill.draft.reviewTitle") }}</h3>
              <p>{{ selectedDraft ? draftDiffSummary(selectedDraft) : t("settings.skill.draft.selectHint") }}</p>
            </div>
            <span v-if="selectedDraft" class="skill-status-pill">{{ draftStatusLabel(selectedDraft) }}</span>
          </header>
          <div v-if="draftDetailLoading" class="settings-state settings-state--compact">{{ t("settings.skill.draft.loadingDetail") }}</div>
          <div v-else-if="draftDetailError" class="settings-state settings-state--error settings-state--compact">{{ draftDetailError }}</div>
          <template v-else-if="selectedDraft">
            <div class="skill-draft-actions">
              <UiButton size="sm" variant="secondary" :disabled="actionLoading === 'draftValidate'" @click="validateSelectedDraft">
                <CheckCircle2 :size="14" /> {{ t("settings.action.validate") }}
              </UiButton>
              <UiButton size="sm" variant="secondary" :disabled="actionLoading === 'draftDiff'" @click="diffSelectedDraft">
                <GitBranch :size="14" /> {{ t("settings.skill.draft.action.diff") }}
              </UiButton>
              <UiButton size="sm" variant="primary" :disabled="actionLoading === 'draftApply'" @click="applySelectedDraft">
                <Shield :size="14" /> {{ t("settings.skill.draft.action.applyOwnerTruth") }}
              </UiButton>
              <UiButton size="sm" variant="secondary" :disabled="actionLoading === 'draftReject'" @click="rejectSelectedDraft">
                {{ t("settings.skill.draft.action.reject") }}
              </UiButton>
              <UiButton size="sm" variant="danger" :disabled="actionLoading === 'draftDelete'" @click="deleteSelectedDraft">
                <Trash2 :size="14" /> {{ t("settings.skill.action.delete") }}
              </UiButton>
            </div>

            <div class="skill-draft-detail-grid">
              <DataTable
                :columns="[fieldColumn, valueColumn]"
                :rows="selectedDraftSummaryRows"
                section-id="skill-draft-summary"
                allow-raw-keys
                :page-size="5"
              />
              <DataTable
                v-if="selectedDraftValidationRows.length"
                :columns="[fieldColumn, valueColumn, countColumn]"
                :rows="selectedDraftValidationRows"
                section-id="skill-draft-validation"
                allow-raw-keys
                :page-size="5"
              />
              <div v-else class="settings-state settings-state--compact">{{ t("settings.skill.draft.validation.notRun") }}</div>
              <DataTable
                v-if="selectedDraftDiffRows.length"
                :columns="[fieldColumn, valueColumn]"
                :rows="selectedDraftDiffRows"
                section-id="skill-draft-diff"
                allow-raw-keys
                :page-size="4"
              />
              <div v-else class="settings-state settings-state--compact">{{ t("settings.skill.draft.diff.notBuilt") }}</div>
            </div>
          </template>
          <div v-else class="settings-state settings-state--compact">{{ t("settings.skill.draft.noSelection") }}</div>
        </article>

        <article class="settings-panel skill-context-card">
          <div class="settings-panel-heading"><h2>{{ t("settings.skill.readiness.title") }}</h2><span><StatusDot :tone="readinessTone(selectedReadiness ?? selectedSkill?.readiness)" />{{ readinessLabel(selectedReadiness ?? selectedSkill?.readiness) }}</span></div>
          <div v-if="readinessError" class="settings-state settings-state--error settings-state--compact">{{ readinessError }}</div>
          <DataTable
            v-if="selectedReadinessRows.length"
            :columns="[fieldColumn, valueColumn]"
            :rows="selectedReadinessRows"
            section-id="skill-readiness"
            allow-raw-keys
            :page-size="5"
          />
          <div v-else class="settings-state settings-state--compact">{{ t("settings.skill.empty.noReadiness") }}</div>
        </article>

        <article class="settings-panel skill-context-card">
          <div class="settings-panel-heading"><h2>{{ t("settings.skill.requirements.title") }}</h2><span>{{ t("settings.skill.ownerTruth") }}</span></div>
          <DataTable
            v-if="selectedRequirementRows.length"
            :columns="[fieldColumn, valueColumn, countColumn]"
            :rows="selectedRequirementRows"
            section-id="skill-requirements"
            allow-raw-keys
            :page-size="5"
          />
          <div v-else class="settings-state settings-state--compact">{{ t("settings.skill.empty.noRequirements") }}</div>
        </article>

        <article class="settings-panel skill-context-card">
          <div class="settings-panel-heading"><h2>{{ t("settings.skill.resources.title") }}</h2><span>{{ selectedResourceRows.length }}</span></div>
          <DataTable
            v-if="selectedResourceRows.length"
            :columns="[pathColumn, kindColumn, sizeColumn]"
            :rows="selectedResourceRows"
            section-id="skill-resources"
            allow-raw-keys
            :page-size="5"
          />
          <div v-else class="settings-state settings-state--compact">{{ t("settings.skill.empty.noResources") }}</div>
        </article>

        <article class="settings-panel skill-context-card">
          <div class="settings-panel-heading"><h2>{{ t("settings.skill.package.title") }}</h2><span>{{ t("settings.skill.ownerTruth") }}</span></div>
          <DataTable
            v-if="selectedPackageRows.length"
            :columns="[fieldColumn, valueColumn]"
            :rows="selectedPackageRows"
            section-id="skill-package-paths"
            allow-raw-keys
            :page-size="5"
          />
          <div v-else class="settings-state settings-state--compact">{{ t("settings.skill.empty.noSelection") }}</div>
        </article>

        <article class="settings-panel skill-context-card">
          <div class="settings-panel-heading"><h2>{{ t("settings.skill.audit.title") }}</h2><span>{{ selectedAuditTableRows.length }}</span></div>
          <DataTable
            v-if="selectedAuditTableRows.length"
            :columns="[timeColumn, actionColumn, statusColumn, sourceColumn, messageColumn]"
            :rows="selectedAuditTableRows"
            section-id="skill-audit"
            allow-raw-keys
            :page-size="5"
          />
          <div v-else class="settings-state settings-state--compact">{{ t("settings.skill.empty.noAudit") }}</div>
        </article>
      </aside>
    </section>

    <footer class="settings-footer skill-footer">
      <span><Package :size="14" />{{ t("settings.skill.footer.owner") }}</span>
      <span><Shield :size="14" />{{ t("settings.skill.footer.settings") }}</span>
      <span><GitBranch :size="14" />{{ t("settings.skill.footer.actions") }}</span>
    </footer>

    <div v-if="sourceDialogOpen" class="skill-modal-backdrop" role="dialog" aria-modal="true">
      <article class="settings-panel skill-modal skill-modal--wide">
        <header class="skill-modal-header">
          <div>
            <h2>{{ t("settings.skill.sources.title") }}</h2>
            <p>{{ sourceRows.length }} · {{ t("settings.skill.ownerApi") }}</p>
          </div>
          <UiButton size="sm" variant="ghost" @click="sourceDialogOpen = false">{{ t("common.cancel") }}</UiButton>
        </header>
        <div v-if="sourceError" class="settings-state settings-state--error settings-state--compact">{{ sourceError }}</div>
        <DataTable
          v-if="sourceRows.length"
          :columns="[sourceColumn, kindColumn, pathColumn, enabledColumn, statusColumn, countColumn, updatedColumn]"
          :rows="sourceRows"
          section-id="skill-sources"
          allow-raw-keys
          clickable-rows
          @row-click="selectSourceResource"
        />
        <div v-else class="settings-state settings-state--compact">{{ t("settings.skill.empty.noSources") }}</div>
        <form class="skill-action-box skill-source-form" @submit.prevent="saveSourceFromOwner">
          <label>
            <span>{{ t("settings.skill.field.sourceId") }}</span>
            <input v-model="sourceForm.sourceId" placeholder="workspace-skills" />
          </label>
          <label class="skill-editor-wide">
            <span>{{ t("settings.skill.field.rootPath") }}</span>
            <input v-model="sourceForm.rootPath" placeholder="/path/to/skills" />
          </label>
          <label>
            <span>{{ t("settings.skill.field.sourceKind") }}</span>
            <select v-model="sourceForm.sourceKind">
              <option value="external">external</option>
              <option value="managed">managed</option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.skill.field.priority") }}</span>
            <input v-model.number="sourceForm.priority" type="number" min="0" />
          </label>
          <label class="skill-checkbox">
            <input v-model="sourceForm.enabled" type="checkbox" />
            <span>{{ t("settings.skill.table.enabled") }}</span>
          </label>
          <label class="skill-checkbox">
            <input v-model="sourceForm.readonly" type="checkbox" />
            <span>{{ t("settings.skill.field.readonly") }}</span>
          </label>
          <div class="skill-form-actions">
            <UiButton size="sm" variant="primary" :disabled="actionLoading === 'createSource' || actionLoading === 'updateSource'" type="submit">
              <Save :size="14" /> {{ t("settings.skill.action.saveSource") }}
            </UiButton>
            <UiButton size="sm" variant="ghost" type="button" @click="clearSourceForm">{{ t("common.reset") }}</UiButton>
            <UiButton size="sm" variant="danger" :disabled="!sourceForm.sourceId || actionLoading === 'deleteSource'" type="button" @click="deleteSourceFromOwner">
              <Trash2 :size="14" /> {{ t("settings.skill.action.deleteSource") }}
            </UiButton>
          </div>
        </form>
      </article>
    </div>

    <div v-if="validateDialogOpen" class="skill-modal-backdrop" role="dialog" aria-modal="true">
      <article class="settings-panel skill-modal">
        <header class="skill-modal-header">
          <div>
            <h2>{{ t("settings.skill.validate.title") }}</h2>
            <p>/skills/validate</p>
          </div>
          <UiButton size="sm" variant="ghost" @click="validateDialogOpen = false">{{ t("common.cancel") }}</UiButton>
        </header>
        <form class="skill-action-box" @submit.prevent="validateFromOwner">
          <label>
            <span>{{ t("settings.skill.field.packagePath") }}</span>
            <input v-model="validatePath" placeholder="/path/to/skill" />
          </label>
          <UiButton size="sm" variant="primary" :disabled="actionLoading === 'validate'" type="submit">
            <CheckCircle2 :size="14" /> {{ t("settings.action.validate") }}
          </UiButton>
        </form>
        <dl v-if="validationResult" class="settings-kv skill-action-result">
          <div><dt>{{ t("settings.skill.validate.validated") }}</dt><dd>{{ validationResult.name }} · {{ validationResult.root_path }}</dd></div>
        </dl>
      </article>
    </div>

    <div v-if="installDialogOpen" class="skill-modal-backdrop" role="dialog" aria-modal="true">
      <article class="settings-panel skill-modal">
        <header class="skill-modal-header">
          <div>
            <h2>{{ t("settings.skill.install.title") }}</h2>
            <p>/skills/install</p>
          </div>
          <UiButton size="sm" variant="ghost" @click="installDialogOpen = false">{{ t("common.cancel") }}</UiButton>
        </header>
        <form class="skill-action-box" @submit.prevent="installFromOwner">
          <label>
            <span>{{ t("settings.skill.field.installSourceDir") }}</span>
            <input v-model="installSourceDir" placeholder="/path/to/skill" />
          </label>
          <label>
            <span>{{ t("settings.skill.field.scope") }}</span>
            <select v-model="installScope">
              <option value="workspace">workspace</option>
              <option value="global">global</option>
            </select>
          </label>
          <label>
            <span>{{ t("settings.skill.field.workspaceDir") }}</span>
            <input v-model="installWorkspaceDir" :disabled="installScope !== 'workspace'" placeholder="/path/to/workspace" />
          </label>
          <UiButton size="sm" variant="primary" :disabled="actionLoading === 'install'" type="submit">
            <Package :size="14" /> {{ t("settings.skill.action.install") }}
          </UiButton>
        </form>
        <dl v-if="installResult" class="settings-kv skill-action-result">
          <div><dt>{{ t("settings.skill.install.installed") }}</dt><dd>{{ installResult.target_path }}</dd></div>
        </dl>
      </article>
    </div>
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
  min-height: 96px;
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
  grid-template-columns: minmax(140px, 180px) minmax(220px, 1fr) minmax(160px, 220px) auto;
  gap: 10px;
  align-items: end;
  margin-bottom: 10px;
}

.skill-query-row label,
.skill-owner-actions label,
.skill-action-box label,
.skill-editor-grid label {
  display: grid;
  gap: 5px;
  min-width: 0;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
}

.skill-query-row input,
.skill-owner-actions input,
.skill-action-box input,
.skill-action-box select,
.skill-editor-grid input,
.skill-editor-grid select,
.skill-instructions textarea {
  min-width: 0;
  min-height: 34px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  padding: 0 10px;
  background: var(--surface-raised);
  color: var(--text-primary);
  font: inherit;
}

.skill-instructions textarea {
  min-height: 360px;
  resize: vertical;
  padding: 10px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.skill-query-row input:disabled,
.skill-action-box input:disabled,
.skill-action-box select:disabled,
.skill-editor-grid input:disabled,
.skill-editor-grid select:disabled {
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

.skill-workspace-grid,
.skill-detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 10px;
  align-items: start;
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

.skill-detail-grid,
.skill-support-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
}

.skill-editor-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.skill-editor-wide {
  grid-column: span 2;
}

.skill-editor-actions,
.skill-form-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.skill-detail-grid article,
.skill-instructions {
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  padding: 12px;
  background: color-mix(in srgb, var(--surface-panel-soft) 72%, transparent);
}

.skill-side-stack,
.skill-owner-actions {
  display: grid;
  gap: 10px;
}

.skill-action-buttons {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
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

.skill-source-form {
  margin-top: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.skill-checkbox {
  display: inline-flex !important;
  grid-auto-flow: column;
  justify-content: start;
  align-items: center;
}

.skill-checkbox input {
  min-height: auto;
}

.skill-support-grid {
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.75fr) minmax(320px, 0.75fr);
  margin-top: 10px;
}

@media (max-width: 1180px) {
  .skill-summary-grid,
  .skill-meta-grid,
  .skill-support-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .skill-workspace-grid,
  .skill-detail-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 780px) {
  .skill-summary-grid,
  .skill-query-row,
  .skill-detail-grid,
  .skill-editor-grid,
  .skill-meta-grid,
  .skill-support-grid {
    grid-template-columns: 1fr;
  }

  .skill-editor-wide {
    grid-column: auto;
  }

  .skill-tabs-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .skill-action-buttons {
    grid-template-columns: 1fr;
  }
}

.skill-console {
  box-sizing: border-box;
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr);
  gap: 8px;
  height: calc(100dvh - var(--shell-topbar-height));
  overflow: hidden;
}

.skill-console-header {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) auto;
  gap: 16px;
  align-items: center;
  min-height: 38px;
}

.skill-title h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: 20px;
  line-height: 1.15;
}

.skill-title p {
  margin-top: 2px;
  color: var(--text-secondary);
  font-size: 11px;
}

.skill-header-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.skill-notice {
  min-height: 38px;
  margin: 0;
  padding: 10px 12px;
}

.skill-command-strip {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  min-width: 0;
}

.skill-kpi-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
  min-width: 0;
}

.skill-kpi-card {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 7px;
  align-items: center;
  min-height: 46px;
  padding: 6px 9px;
}

.skill-kpi-card > span {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border: 1px solid color-mix(in srgb, var(--color-accent) 32%, transparent);
  border-radius: var(--radius-2);
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 9%, transparent);
}

.skill-kpi-card small {
  display: block;
  color: var(--text-muted);
  font-size: 9.5px;
  font-weight: 800;
  text-transform: uppercase;
}

.skill-kpi-card strong {
  display: block;
  margin-top: 0;
  color: var(--text-primary);
  font-size: 18px;
  line-height: 1;
}

.skill-draft-queue,
.skill-draft-review {
  min-width: 0;
}

.skill-draft-queue {
  min-height: 0;
  overflow: auto;
}

.skill-draft-queue :deep(.data-table--skill-drafts) {
  max-width: 100%;
  --data-table-min-width: 640px;
}

.skill-draft-queue :deep(.data-table--skill-drafts th),
.skill-draft-queue :deep(.data-table--skill-drafts td) {
  padding-inline: 6px;
  font-size: 11px;
}

.skill-draft-review {
  display: grid;
  align-content: start;
  gap: 9px;
  min-height: 0;
  overflow: hidden;
}

.skill-draft-review > header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.skill-draft-review h3 {
  display: flex;
  gap: 7px;
  align-items: center;
  margin: 0;
  color: var(--text-primary);
  font-size: 13px;
}

.skill-draft-review p {
  margin-top: 3px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.45;
}

.skill-draft-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  align-items: center;
}

.skill-draft-detail-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  min-height: 0;
  overflow: auto;
}

.skill-draft-detail-grid > :last-child {
  grid-column: auto;
}

.skill-workbench-grid {
  display: grid;
  grid-template-columns: minmax(330px, 0.8fr) minmax(560px, 1.36fr) minmax(340px, 0.84fr);
  grid-template-rows: minmax(0, 1fr);
  grid-template-areas:
    "catalog editor side";
  gap: 8px;
  min-height: 0;
  min-width: 0;
}

.skill-catalog-panel,
.skill-editor-panel,
.skill-context-stack,
.skill-context-card,
.skill-owner-actions {
  min-width: 0;
}

.skill-catalog-panel {
  grid-area: catalog;
}

.skill-editor-panel {
  grid-area: editor;
}

.skill-context-stack {
  grid-area: side;
}

.skill-catalog-panel,
.skill-editor-panel {
  display: grid;
  gap: 8px;
  overflow: hidden;
}

.skill-catalog-panel {
  grid-template-rows: auto auto minmax(0, 1fr) minmax(160px, 0.42fr);
}

.skill-editor-panel {
  grid-template-rows: auto auto auto minmax(0, 1fr);
}

.skill-panel-head,
.skill-editor-header,
.skill-modal-header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.skill-panel-head h2,
.skill-editor-header h2,
.skill-modal-header h2 {
  display: flex;
  gap: 7px;
  align-items: center;
  margin: 0;
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.2;
}

.skill-panel-head p,
.skill-editor-header p,
.skill-modal-header p {
  margin-top: 2px;
  color: var(--text-secondary);
  font-size: 10.5px;
  line-height: 1.35;
}

.skill-panel-head--compact {
  align-items: center;
  padding-top: 6px;
  border-top: 1px solid var(--border-subtle);
}

.skill-panel-head--compact h2 {
  font-size: 14px;
}

.skill-panel-head > span,
.skill-status-pill {
  display: inline-flex;
  flex: 0 0 auto;
  gap: 5px;
  align-items: center;
  min-height: 22px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-1);
  padding: 2px 7px;
  color: var(--text-secondary);
  font-size: 11px;
  white-space: nowrap;
}

.skill-filter-grid {
  display: grid;
  grid-template-columns: minmax(220px, 1.15fr) minmax(120px, 0.56fr) minmax(280px, 1.2fr) minmax(150px, 0.64fr) auto;
  gap: 8px;
  align-items: center;
  align-content: start;
  padding: 6px 8px;
}

.skill-filter-wide {
  grid-column: auto;
}

.skill-filter-grid label {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 7px;
  align-items: center;
  min-width: 0;
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 750;
}

.skill-editor-grid label,
.skill-owner-actions label,
.skill-action-box label {
  display: grid;
  gap: 3px;
  min-width: 0;
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 750;
}

.skill-filter-grid input,
.skill-editor-grid input,
.skill-editor-grid select,
.skill-owner-actions input,
.skill-action-box input,
.skill-action-box select,
.skill-instructions textarea {
  min-width: 0;
  min-height: 28px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  padding: 0 9px;
  background: var(--surface-raised);
  color: var(--text-primary);
  font: inherit;
}

.skill-filter-grid input:disabled,
.skill-editor-grid input:disabled,
.skill-editor-grid select:disabled,
.skill-action-box input:disabled,
.skill-action-box select:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.skill-tabs {
  min-height: 28px;
  margin-bottom: 0;
}

.skill-table-frame {
  min-height: 0;
  max-width: 100%;
  overflow: auto;
  border-top: 1px solid var(--border-subtle);
  padding-top: 2px;
}

.skill-draft-queue-section {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 6px;
  min-height: 0;
  overflow: hidden;
}

.skill-table-frame :deep(.data-table--skill-catalog) {
  max-width: 100%;
  --data-table-min-width: 720px;
}

.skill-table-frame :deep(.data-table--skill-catalog th),
.skill-table-frame :deep(.data-table--skill-catalog td) {
  padding-inline: 6px;
  font-size: 11px;
}

.skill-table-frame :deep(.data-table--skill-catalog .column-skill) {
  width: 138px;
}

.skill-table-frame :deep(.data-table--skill-catalog .column-source),
.skill-table-frame :deep(.data-table--skill-catalog .column-enabled),
.skill-table-frame :deep(.data-table--skill-catalog .column-ready),
.skill-table-frame :deep(.data-table--skill-catalog .column-surface),
.skill-table-frame :deep(.data-table--skill-catalog .column-access) {
  width: 76px;
}

.skill-table-frame :deep(.data-table--skill-catalog .column-tools) {
  width: 132px;
}

.skill-table-frame :deep(.data-table--skill-catalog .column-updated) {
  width: 78px;
}

.skill-table-frame :deep(td:first-child) {
  color: var(--text-primary);
  font-weight: 760;
}

.skill-meta-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.skill-meta-strip span {
  display: grid;
  gap: 2px;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  padding: 5px 7px;
  background: color-mix(in srgb, var(--surface-panel-soft) 72%, transparent);
  color: var(--text-secondary);
  font-size: 10.5px;
  overflow-wrap: anywhere;
}

.skill-meta-strip strong {
  color: var(--text-muted);
  font-size: 9.5px;
  text-transform: uppercase;
}

.skill-editor-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}

.skill-editor-wide {
  grid-column: span 2;
}

.skill-inline-actions,
.skill-form-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.skill-instructions {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 6px;
  min-width: 0;
  min-height: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  padding: 8px;
  background: color-mix(in srgb, var(--surface-panel-soft) 72%, transparent);
}

.skill-instructions textarea {
  min-height: 0;
  height: 100%;
  resize: vertical;
  padding: 9px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
}

.skill-context-stack {
  display: grid;
  grid-auto-rows: max-content;
  align-content: start;
  gap: 10px;
  min-height: 0;
  overflow: auto;
}

.skill-context-card,
.skill-owner-actions {
  display: grid;
  align-content: start;
  gap: 9px;
  overflow: hidden;
}

.skill-action-buttons {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.skill-context-card :deep(.data-table) {
  --data-table-min-width: 420px;
  font-size: 11px;
}

.skill-action-box {
  display: grid;
  gap: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-2);
  padding: 10px;
  background: color-mix(in srgb, var(--surface-panel-soft) 72%, transparent);
}

.skill-source-form {
  margin-top: 10px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.skill-checkbox {
  display: inline-flex !important;
  grid-auto-flow: column;
  justify-content: start;
  align-items: center;
}

.skill-checkbox input {
  min-height: auto;
}

.skill-action-result {
  border-top: 1px solid var(--border-subtle);
  padding-top: 8px;
}

.skill-footer {
  margin-top: 0;
}

.skill-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 24px;
  background: color-mix(in srgb, var(--surface-backdrop, #020617) 62%, transparent);
  backdrop-filter: blur(10px);
}

.skill-modal {
  display: grid;
  gap: 12px;
  width: min(720px, 100%);
  max-height: calc(100vh - 48px);
  overflow: auto;
}

.skill-modal--wide {
  width: min(1120px, 100%);
}

@media (max-width: 1380px) {
  .skill-command-strip {
    grid-template-columns: 1fr;
  }

  .skill-kpi-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .skill-workbench-grid {
    grid-template-columns: minmax(330px, 0.9fr) minmax(520px, 1.2fr);
    grid-template-rows: minmax(0, 1fr) auto;
    grid-template-areas:
      "catalog editor"
      "side side";
  }

  .skill-context-stack {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    overflow: visible;
  }

  .skill-owner-actions {
    grid-column: span 3;
  }
}

@media (max-width: 1040px) {
  .skill-console-header,
  .skill-workbench-grid {
    grid-template-columns: 1fr;
    grid-template-rows: auto;
    grid-template-areas:
      "catalog"
      "editor"
      "side";
  }

  .skill-console {
    height: auto;
    min-height: calc(100dvh - var(--shell-topbar-height));
    overflow: auto;
  }

  .skill-header-actions {
    justify-content: flex-start;
  }

  .skill-kpi-strip,
  .skill-context-stack {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .skill-owner-actions {
    grid-column: auto;
  }

  .skill-filter-grid,
  .skill-editor-grid,
  .skill-source-form,
  .skill-draft-detail-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .skill-filter-wide {
    grid-column: span 2;
  }
}

@media (max-width: 720px) {
  .skill-kpi-strip,
  .skill-filter-grid,
  .skill-editor-grid,
  .skill-meta-strip,
  .skill-context-stack,
  .skill-source-form,
  .skill-draft-detail-grid {
    grid-template-columns: 1fr;
  }

  .skill-editor-wide {
    grid-column: auto;
  }

  .skill-filter-wide {
    grid-column: auto;
  }

  .skill-action-buttons {
    grid-template-columns: 1fr;
  }

  .skill-modal-backdrop {
    padding: 10px;
  }
}
</style>
