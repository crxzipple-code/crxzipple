import { requestJson } from "@/shared/api/client";

export type SkillInstallScopeApiPayload = "workspace" | "global";
export type SkillReadinessStatusApiPayload =
  | "ready"
  | "setup_needed"
  | "unsupported"
  | "disabled"
  | "invalid"
  | "unknown";
export type SkillDraftStatusApiPayload =
  | "draft"
  | "validated"
  | "invalid"
  | "applied"
  | "rejected"
  | "expired";
export type SkillDraftIntentApiPayload = "create" | "update";

export interface SkillManifestApiPayload {
  api_version: string;
  kind: string;
  name: string;
  description: string;
  version: string | null;
  tags: string[];
  when_to_use: string | null;
  anti_patterns: string[];
  instructions_path: string;
  required_tools: string[];
  optional_tools: string[];
  suggested_tools: string[];
  required_effects: string[];
  required_access: string[];
  surfaces: string[];
  supported_platforms: string[];
  setup_hints: string[];
}

export interface SkillResourceApiPayload {
  path: string;
  kind: string;
  size_bytes: number;
}

export interface SkillRequirementsApiPayload {
  required_tools: string[];
  optional_tools: string[];
  suggested_tools: string[];
  required_effects: string[];
  surfaces: string[];
  supported_platforms: string[];
  required_access: string[];
  setup_hints: string[];
}

export interface SkillEnablementApiPayload {
  enabled?: boolean;
  status?: string | null;
  reason?: string | null;
  policy_id?: string | null;
  scope?: string | null;
  updated_at?: string | null;
}

export interface SkillReadinessApiPayload {
  status?: SkillReadinessStatusApiPayload | string | null;
  ready?: boolean | null;
  missing_tools?: string[];
  missing_access?: string[];
  missing_effects?: string[];
  unsupported_surfaces?: string[];
  unsupported_platforms?: string[];
  validation_errors?: string[];
  setup_hints?: string[];
  checked_at?: string | null;
  updated_at?: string | null;
}

export interface SkillSourceApiPayload {
  source_id: string;
  name?: string | null;
  root_path?: string | null;
  source_kind?: string | null;
  kind?: string | null;
  scope?: string | null;
  priority?: number | null;
  enabled?: boolean | null;
  readonly?: boolean | null;
  status?: string | null;
  last_synced_at?: string | null;
  updated_at?: string | null;
  package_count?: number | null;
  sync_status?: string | null;
}

export interface SkillApiPayload {
  name: string;
  description: string;
  version: string | null;
  tags: string[];
  source: string;
  root_path: string;
  manifest_path: string;
  instructions_path: string;
  resources: SkillResourceApiPayload[];
  requirements: SkillRequirementsApiPayload;
  manifest: SkillManifestApiPayload;
  enabled?: boolean | null;
  updated_at?: string | null;
  enablement?: SkillEnablementApiPayload | null;
  readiness?: SkillReadinessApiPayload | null;
  source_id?: string | null;
  source_status?: string | null;
}

export interface SkillDetailApiPayload extends SkillApiPayload {
  instructions: string | null;
}

export interface ValidateSkillRequestPayload {
  path: string;
}

export interface InstallSkillRequestPayload {
  source_dir: string;
  scope: SkillInstallScopeApiPayload;
  workspace_dir?: string | null;
}

export interface CreateSkillRequestPayload {
  name: string;
  description: string;
  instructions: string;
  scope: SkillInstallScopeApiPayload;
  workspace_dir?: string | null;
  version?: string | null;
  tags?: string[];
  required_tools?: string[];
  optional_tools?: string[];
  suggested_tools?: string[];
  required_effects?: string[];
  required_access?: string[];
  surfaces?: string[];
  supported_platforms?: string[];
  setup_hints?: string[];
}

export interface UpdateSkillRequestPayload {
  workspace_dir?: string | null;
  description?: string | null;
  version?: string | null;
  tags?: string[] | null;
  required_tools?: string[] | null;
  optional_tools?: string[] | null;
  suggested_tools?: string[] | null;
  required_effects?: string[] | null;
  required_access?: string[] | null;
  surfaces?: string[] | null;
  supported_platforms?: string[] | null;
  setup_hints?: string[] | null;
}

export interface SkillWriteRequestPayload {
  content: string;
  workspace_dir?: string | null;
}

export interface SkillEnableRequestPayload {
  workspace_dir?: string | null;
  surface?: string | null;
  reason?: string | null;
}

export interface SkillDisableRequestPayload {
  workspace_dir?: string | null;
  surface?: string | null;
  reason?: string | null;
}

export interface SkillSyncRequestPayload {
  workspace_dir?: string | null;
  source_id?: string | null;
  surface?: string | null;
}

export interface CreateSkillSourceRequestPayload {
  source_id: string;
  root_path: string;
  source_kind?: "managed" | "external";
  enabled?: boolean;
  readonly?: boolean;
  priority?: number;
  metadata?: Record<string, unknown>;
}

export interface UpdateSkillSourceRequestPayload {
  root_path?: string | null;
  enabled?: boolean | null;
  readonly?: boolean | null;
  priority?: number | null;
  metadata?: Record<string, unknown> | null;
}

export interface SkillInstallApiPayload {
  scope: SkillInstallScopeApiPayload;
  target_root: string;
  target_path: string;
  skill: SkillApiPayload;
}

export interface SkillSyncApiPayload {
  source_id: string | null;
  synced_count: number;
  skills: SkillApiPayload[];
}

export interface SkillMutationApiPayload {
  action: string;
  changed: boolean;
  message: string;
  skill: SkillApiPayload;
}

export interface SkillSourceMutationApiPayload {
  action: string;
  changed: boolean;
  message: string;
  source: SkillSourceApiPayload;
}

export interface SkillInstallationApiPayload {
  installation_id: string;
  action: string;
  status: string;
  source_id?: string | null;
  skill_id?: string | null;
  skill_name?: string | null;
  source_uri?: string | null;
  target_uri?: string | null;
  actor_id?: string | null;
  reason?: string | null;
  message?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
}

export interface SkillDraftSupportFileApiPayload {
  path: string;
  content?: string | null;
  content_type?: string | null;
}

export interface SkillDraftValidationApiPayload {
  errors: string[];
  warnings: string[];
  missing_tools: string[];
  missing_access: string[];
  missing_effects: string[];
  unsupported_surfaces: string[];
  unsupported_platforms: string[];
  readiness_status?: SkillReadinessStatusApiPayload | string | null;
}

export interface SkillDraftFileDiffApiPayload {
  path: string;
  status?: string | null;
  summary?: string | string[] | null;
  diff?: string | null;
}

export interface SkillDraftDiffApiPayload {
  manifest_diff?: string | Record<string, unknown> | null;
  instructions_diff?: string | null;
  file_diffs: SkillDraftFileDiffApiPayload[];
  summary?: string | string[] | null;
}

export interface SkillDraftApiPayload {
  draft_id: string;
  status: SkillDraftStatusApiPayload | string;
  intent: SkillDraftIntentApiPayload | string;
  skill_name: string;
  target_source_id?: string | null;
  target_scope?: SkillInstallScopeApiPayload | string | null;
  workspace_dir?: string | null;
  base_fingerprint?: string | null;
  manifest?: Partial<SkillManifestApiPayload> & Record<string, unknown>;
  instructions_body?: string | null;
  support_files?: SkillDraftSupportFileApiPayload[];
  requirements?: Partial<SkillRequirementsApiPayload> & Record<string, unknown>;
  validation?: SkillDraftValidationApiPayload | null;
  diff?: SkillDraftDiffApiPayload | null;
  created_by_run_id?: string | null;
  created_by_turn_id?: string | null;
  actor?: string | null;
  reason?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  expires_at?: string | null;
  audit?: SkillInstallationApiPayload[];
}

export interface SkillDraftQueryParams {
  status?: string | null;
  skillName?: string | null;
  runId?: string | null;
  workspaceDir?: string | null;
}

export interface CreateSkillDraftRequestPayload {
  intent: SkillDraftIntentApiPayload;
  skill_name: string;
  summary?: string | null;
  target_source_id?: string | null;
  target_scope?: SkillInstallScopeApiPayload | string | null;
  workspace_dir?: string | null;
  manifest?: Record<string, unknown>;
  instructions_body?: string | null;
  support_files?: SkillDraftSupportFileApiPayload[];
  requirements?: Record<string, unknown>;
  reason?: string | null;
  created_by_run_id?: string | null;
  created_by_turn_id?: string | null;
}

export type UpdateSkillDraftRequestPayload = Partial<CreateSkillDraftRequestPayload> & {
  status?: SkillDraftStatusApiPayload | string | null;
};

export interface SkillDraftReasonRequestPayload {
  reason?: string | null;
}

export interface SkillQueryParams {
  workspaceDir?: string | null;
  surface?: string | null;
  source?: string | null;
  includeDisabled?: boolean;
  includeReadiness?: boolean;
  includeRemoved?: boolean;
}

export interface SkillDetailQueryParams extends SkillQueryParams {
  includeInstructions?: boolean;
}

export async function listSkills(params: SkillQueryParams = {}): Promise<SkillApiPayload[]> {
  const payload = await requestJson<SkillApiPayload[]>(`/skills${skillQuery(params)}`);
  return payload.map(normalizeSkill);
}

export async function getSkill(
  skillName: string,
  params: SkillDetailQueryParams = {},
): Promise<SkillDetailApiPayload> {
  const payload = await requestJson<SkillDetailApiPayload>(
    `/skills/${encodeURIComponent(skillName)}${skillQuery(params)}`,
  );
  return normalizeSkill(payload) as SkillDetailApiPayload;
}

export async function validateSkill(path: string): Promise<SkillApiPayload> {
  const payload = await requestJson<SkillApiPayload>("/skills/validate", {
    method: "POST",
    body: JSON.stringify({ path } satisfies ValidateSkillRequestPayload),
  });
  return normalizeSkill(payload);
}

export async function installSkill(payload: InstallSkillRequestPayload): Promise<SkillInstallApiPayload> {
  const result = await requestJson<SkillInstallApiPayload>("/skills/install", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return normalizeSkillInstall(result);
}

export async function createSkill(payload: CreateSkillRequestPayload): Promise<SkillMutationApiPayload> {
  const result = await requestJson<SkillMutationApiPayload>("/skills", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return normalizeSkillMutation(result);
}

export async function updateSkill(
  skillName: string,
  payload: UpdateSkillRequestPayload,
): Promise<SkillMutationApiPayload> {
  const result = await requestJson<SkillMutationApiPayload>(`/skills/${encodeURIComponent(skillName)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return normalizeSkillMutation(result);
}

export async function writeSkillInstructions(
  skillName: string,
  payload: SkillWriteRequestPayload,
): Promise<SkillMutationApiPayload> {
  const result = await requestJson<SkillMutationApiPayload>(
    `/skills/${encodeURIComponent(skillName)}/instructions`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
  return normalizeSkillMutation(result);
}

export async function writeSkillFile(
  skillName: string,
  filePath: string,
  payload: SkillWriteRequestPayload,
): Promise<SkillMutationApiPayload> {
  const result = await requestJson<SkillMutationApiPayload>(
    `/skills/${encodeURIComponent(skillName)}/files/${skillFilePath(filePath)}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
  return normalizeSkillMutation(result);
}

export async function deleteSkillFile(
  skillName: string,
  filePath: string,
  params: SkillQueryParams = {},
): Promise<SkillMutationApiPayload> {
  const result = await requestJson<SkillMutationApiPayload>(
    `/skills/${encodeURIComponent(skillName)}/files/${skillFilePath(filePath)}${skillQuery(params)}`,
    {
      method: "DELETE",
    },
  );
  return normalizeSkillMutation(result);
}

export async function enableSkill(
  skillName: string,
  payload: SkillEnableRequestPayload = {},
): Promise<SkillMutationApiPayload> {
  const result = await requestJson<SkillMutationApiPayload>(`/skills/${encodeURIComponent(skillName)}/enable`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return normalizeSkillMutation(result);
}

export async function disableSkill(
  skillName: string,
  payload: SkillDisableRequestPayload = {},
): Promise<SkillMutationApiPayload> {
  const result = await requestJson<SkillMutationApiPayload>(`/skills/${encodeURIComponent(skillName)}/disable`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return normalizeSkillMutation(result);
}

export async function deleteSkill(
  skillName: string,
  params: SkillQueryParams = {},
): Promise<SkillMutationApiPayload> {
  const result = await requestJson<SkillMutationApiPayload>(
    `/skills/${encodeURIComponent(skillName)}${skillQuery(params)}`,
    {
      method: "DELETE",
    },
  );
  return normalizeSkillMutation(result);
}

export async function syncSkills(payload: SkillSyncRequestPayload = {}): Promise<SkillSyncApiPayload> {
  const result = await requestJson<SkillSyncApiPayload>("/skills/sync", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return {
    ...result,
    skills: result.skills.map(normalizeSkill),
  };
}

export function listSkillSources(params: SkillQueryParams = {}): Promise<SkillSourceApiPayload[]> {
  return requestJson<SkillSourceApiPayload[]>(`/skills/sources${skillQuery(params)}`);
}

export function listSkillInstallations(params: {
  skillName?: string | null;
  sourceId?: string | null;
  limit?: number;
} = {}): Promise<SkillInstallationApiPayload[]> {
  const query = new URLSearchParams();
  const skillName = params.skillName?.trim();
  const sourceId = params.sourceId?.trim();
  if (skillName) query.set("skill_name", skillName);
  if (sourceId) query.set("source_id", sourceId);
  if (params.limit) query.set("limit", String(params.limit));
  const text = query.toString();
  return requestJson<SkillInstallationApiPayload[]>(`/skills/installations${text ? `?${text}` : ""}`);
}

export async function listSkillDrafts(params: SkillDraftQueryParams = {}): Promise<SkillDraftApiPayload[]> {
  const payload = await requestJson<SkillDraftApiPayload[] | { drafts?: SkillDraftApiPayload[]; items?: SkillDraftApiPayload[] }>(
    `/skills/drafts${skillDraftQuery(params)}`,
  );
  const drafts = Array.isArray(payload) ? payload : payload.drafts ?? payload.items ?? [];
  return drafts.map(normalizeSkillDraft);
}

export async function getSkillDraft(draftId: string): Promise<SkillDraftApiPayload> {
  const payload = await requestJson<SkillDraftApiPayload>(`/skills/drafts/${encodeURIComponent(draftId)}`);
  return normalizeSkillDraft(payload);
}

export async function createSkillDraft(
  payload: CreateSkillDraftRequestPayload,
): Promise<SkillDraftApiPayload> {
  const result = await requestJson<SkillDraftApiPayload>("/skills/drafts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return normalizeSkillDraft(result);
}

export async function updateSkillDraft(
  draftId: string,
  payload: UpdateSkillDraftRequestPayload,
): Promise<SkillDraftApiPayload> {
  const result = await requestJson<SkillDraftApiPayload>(`/skills/drafts/${encodeURIComponent(draftId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return normalizeSkillDraft(result);
}

export async function validateSkillDraft(draftId: string): Promise<SkillDraftApiPayload> {
  const result = await requestJson<SkillDraftApiPayload>(`/skills/drafts/${encodeURIComponent(draftId)}/validate`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return normalizeSkillDraft(result);
}

export async function diffSkillDraft(draftId: string): Promise<SkillDraftApiPayload> {
  const result = await requestJson<SkillDraftApiPayload>(`/skills/drafts/${encodeURIComponent(draftId)}/diff`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return normalizeSkillDraft(result);
}

export async function applySkillDraft(
  draftId: string,
  payload: SkillDraftReasonRequestPayload = {},
): Promise<SkillDraftApiPayload> {
  const result = await requestJson<SkillDraftApiPayload>(`/skills/drafts/${encodeURIComponent(draftId)}/apply`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return normalizeSkillDraft(result);
}

export async function rejectSkillDraft(
  draftId: string,
  payload: SkillDraftReasonRequestPayload = {},
): Promise<SkillDraftApiPayload> {
  const result = await requestJson<SkillDraftApiPayload>(`/skills/drafts/${encodeURIComponent(draftId)}/reject`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return normalizeSkillDraft(result);
}

export async function deleteSkillDraft(draftId: string): Promise<SkillDraftApiPayload> {
  const result = await requestJson<SkillDraftApiPayload>(`/skills/drafts/${encodeURIComponent(draftId)}`, {
    method: "DELETE",
  });
  return normalizeSkillDraft(result);
}

export function createSkillSource(
  payload: CreateSkillSourceRequestPayload,
): Promise<SkillSourceMutationApiPayload> {
  return requestJson<SkillSourceMutationApiPayload>("/skills/sources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateSkillSource(
  sourceId: string,
  payload: UpdateSkillSourceRequestPayload,
): Promise<SkillSourceMutationApiPayload> {
  return requestJson<SkillSourceMutationApiPayload>(`/skills/sources/${encodeURIComponent(sourceId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteSkillSource(sourceId: string): Promise<SkillSourceMutationApiPayload> {
  return requestJson<SkillSourceMutationApiPayload>(`/skills/sources/${encodeURIComponent(sourceId)}`, {
    method: "DELETE",
  });
}

export async function getSkillReadiness(
  skillName: string,
  params: SkillQueryParams = {},
): Promise<SkillReadinessApiPayload> {
  const payload = await requestJson<SkillReadinessApiPayload>(
    `/skills/${encodeURIComponent(skillName)}/readiness${skillQuery(params)}`,
  );
  return normalizeReadiness(payload);
}

function skillQuery(params: SkillDetailQueryParams): string {
  const query = new URLSearchParams();
  const workspaceDir = params.workspaceDir?.trim();
  const surface = params.surface?.trim();
  const source = params.source?.trim();
  if (workspaceDir) query.set("workspace_dir", workspaceDir);
  if (surface) query.set("surface", surface);
  if (source) query.set("source", source);
  if (params.includeDisabled) query.set("include_disabled", "true");
  if (params.includeReadiness) query.set("include_readiness", "true");
  if (params.includeRemoved) query.set("include_removed", "true");
  if (params.includeInstructions) query.set("include_instructions", "true");
  const text = query.toString();
  return text ? `?${text}` : "";
}

function skillDraftQuery(params: SkillDraftQueryParams): string {
  const query = new URLSearchParams();
  const status = params.status?.trim();
  const skillName = params.skillName?.trim();
  const runId = params.runId?.trim();
  const workspaceDir = params.workspaceDir?.trim();
  if (status) query.set("status", status);
  if (skillName) query.set("skill_name", skillName);
  if (runId) query.set("run_id", runId);
  if (workspaceDir) query.set("workspace_dir", workspaceDir);
  const text = query.toString();
  return text ? `?${text}` : "";
}

function skillFilePath(path: string): string {
  return path.split("/").map((part) => encodeURIComponent(part)).join("/");
}

function normalizeSkill(skill: SkillApiPayload): SkillApiPayload {
  const requirements = skill.requirements ?? ({} as SkillRequirementsApiPayload);
  const manifest = skill.manifest ?? ({} as SkillManifestApiPayload);
  return {
    ...skill,
    tags: stringArray(skill.tags),
    resources: Array.isArray(skill.resources) ? skill.resources : [],
    requirements: {
      required_tools: stringArray(requirements.required_tools),
      optional_tools: stringArray(requirements.optional_tools),
      suggested_tools: stringArray(requirements.suggested_tools),
      required_effects: stringArray(requirements.required_effects),
      surfaces: stringArray(requirements.surfaces),
      supported_platforms: stringArray(requirements.supported_platforms),
      required_access: stringArray(requirements.required_access),
      setup_hints: stringArray(requirements.setup_hints),
    },
    manifest: {
      api_version: stringValue(manifest.api_version, "skills.crxzipple/v1alpha1"),
      kind: stringValue(manifest.kind, "Skill"),
      name: stringValue(manifest.name, skill.name),
      description: stringValue(manifest.description, skill.description),
      version: manifest.version ?? null,
      tags: stringArray(manifest.tags),
      when_to_use: manifest.when_to_use ?? null,
      anti_patterns: stringArray(manifest.anti_patterns),
      instructions_path: stringValue(manifest.instructions_path, skill.instructions_path),
      required_tools: stringArray(manifest.required_tools),
      optional_tools: stringArray(manifest.optional_tools),
      suggested_tools: stringArray(manifest.suggested_tools),
      required_effects: stringArray(manifest.required_effects),
      required_access: stringArray(manifest.required_access),
      surfaces: stringArray(manifest.surfaces),
      supported_platforms: stringArray(manifest.supported_platforms),
      setup_hints: stringArray(manifest.setup_hints),
    },
    readiness: skill.readiness ? normalizeReadiness(skill.readiness) : null,
  };
}

function normalizeReadiness(readiness: SkillReadinessApiPayload): SkillReadinessApiPayload {
  return {
    ...readiness,
    missing_tools: stringArray(readiness.missing_tools),
    missing_access: stringArray(readiness.missing_access),
    missing_effects: stringArray(readiness.missing_effects),
    unsupported_surfaces: stringArray(readiness.unsupported_surfaces),
    unsupported_platforms: stringArray(readiness.unsupported_platforms),
    validation_errors: stringArray(readiness.validation_errors),
    setup_hints: stringArray(readiness.setup_hints),
  };
}

function normalizeSkillMutation(result: SkillMutationApiPayload): SkillMutationApiPayload {
  return {
    ...result,
    skill: normalizeSkill(result.skill),
  };
}

function normalizeSkillInstall(result: SkillInstallApiPayload): SkillInstallApiPayload {
  return {
    ...result,
    skill: normalizeSkill(result.skill),
  };
}

function normalizeSkillDraft(draft: SkillDraftApiPayload): SkillDraftApiPayload {
  return {
    ...draft,
    draft_id: stringValue(draft.draft_id),
    status: stringValue(draft.status, "draft"),
    intent: stringValue(draft.intent, "create"),
    skill_name: stringValue(draft.skill_name),
    support_files: Array.isArray(draft.support_files) ? draft.support_files : [],
    validation: draft.validation ? normalizeSkillDraftValidation(draft.validation) : null,
    diff: draft.diff ? normalizeSkillDraftDiff(draft.diff) : null,
    audit: Array.isArray(draft.audit) ? draft.audit : [],
  };
}

function normalizeSkillDraftValidation(validation: SkillDraftValidationApiPayload): SkillDraftValidationApiPayload {
  return {
    ...validation,
    errors: stringArray(validation.errors),
    warnings: stringArray(validation.warnings),
    missing_tools: stringArray(validation.missing_tools),
    missing_access: stringArray(validation.missing_access),
    missing_effects: stringArray(validation.missing_effects),
    unsupported_surfaces: stringArray(validation.unsupported_surfaces),
    unsupported_platforms: stringArray(validation.unsupported_platforms),
  };
}

function normalizeSkillDraftDiff(diff: SkillDraftDiffApiPayload): SkillDraftDiffApiPayload {
  return {
    ...diff,
    file_diffs: Array.isArray(diff.file_diffs) ? diff.file_diffs : [],
  };
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item.trim() : String(item).trim()))
    .filter(Boolean);
}

function stringValue(value: unknown, fallback = ""): string {
  if (typeof value === "string" && value.trim()) return value;
  return fallback;
}
