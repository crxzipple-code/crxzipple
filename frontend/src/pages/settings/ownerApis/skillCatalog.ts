import { requestJson } from "@/shared/api/client";

export type SkillInstallScopeApiPayload = "workspace" | "global";

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
  surfaces: string[];
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
  compatibility_auth: string[];
  compatibility_secrets: string[];
  compatibility_credential_files: string[];
  setup_hints: string[];
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

export interface SkillInstallApiPayload {
  scope: SkillInstallScopeApiPayload;
  target_root: string;
  target_path: string;
  skill: SkillApiPayload;
}

export interface SkillQueryParams {
  workspaceDir?: string | null;
  surface?: string | null;
}

export interface SkillDetailQueryParams extends SkillQueryParams {
  includeInstructions?: boolean;
}

export function listSkills(params: SkillQueryParams = {}): Promise<SkillApiPayload[]> {
  return requestJson<SkillApiPayload[]>(`/skills${skillQuery(params)}`);
}

export function getSkill(
  skillName: string,
  params: SkillDetailQueryParams = {},
): Promise<SkillDetailApiPayload> {
  return requestJson<SkillDetailApiPayload>(
    `/skills/${encodeURIComponent(skillName)}${skillQuery(params)}`,
  );
}

export function validateSkill(path: string): Promise<SkillApiPayload> {
  return requestJson<SkillApiPayload>("/skills/validate", {
    method: "POST",
    body: JSON.stringify({ path } satisfies ValidateSkillRequestPayload),
  });
}

export function installSkill(payload: InstallSkillRequestPayload): Promise<SkillInstallApiPayload> {
  return requestJson<SkillInstallApiPayload>("/skills/install", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

function skillQuery(params: SkillDetailQueryParams): string {
  const query = new URLSearchParams();
  const workspaceDir = params.workspaceDir?.trim();
  const surface = params.surface?.trim();
  if (workspaceDir) query.set("workspace_dir", workspaceDir);
  if (surface) query.set("surface", surface);
  if (params.includeInstructions) query.set("include_instructions", "true");
  const text = query.toString();
  return text ? `?${text}` : "";
}
