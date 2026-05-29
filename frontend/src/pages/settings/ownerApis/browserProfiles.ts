import { requestJson } from "@/shared/api/client";

export interface BrowserProfileApiPayload {
  name: string;
  driver: string;
  enabled?: boolean;
  attach_only: boolean;
  configured_cdp_url?: string | null;
  configured_cdp_port?: number | null;
  resolved_cdp_url?: string | null;
  resolved_cdp_port?: number | null;
  user_data_dir?: string | null;
  profile_directory?: string | null;
  autostart?: boolean;
  mode?: string | null;
  proxy?: {
    mode?: string | null;
    server?: string | null;
    bypass_list?: string[];
    binding_id?: string | null;
    credential_kind?: string | null;
  };
  close_targets_on_release?: boolean;
  close_targets_on_expire?: boolean;
  runtime?: {
    attachment_status?: string;
    browser_ref?: string | null;
    running_pid?: number | null;
    last_error?: string | null;
    proxy_egress?: Record<string, unknown>;
    proxy_egress_status?: string | null;
    proxy_egress_ip?: string | null;
    proxy_egress_checked_at?: string | null;
  } | null;
  diagnostics?: {
    status?: string;
    summary?: {
      code?: string;
      label?: string;
      severity?: string;
    };
    summary_line?: string;
    message?: string;
    recommended_action?: string;
    ready?: boolean;
    restart_needed?: boolean;
    restart_fields?: string[];
    probe?: {
      status?: string;
      message?: string;
      mismatch_reason?: string;
      mismatch_fields?: string[];
      conflict_pid?: number | string | null;
    };
  };
}

export interface BrowserProfilesApiPayload {
  enabled: boolean;
  default_profile: string;
  profiles: BrowserProfileApiPayload[];
}

export interface BrowserProfilePoolApiPayload {
  pool_id: string;
  display_name?: string | null;
  enabled: boolean;
  profile_names: string[];
  target_hosts: string[];
  selection_strategy: string;
  max_concurrency_per_profile: number;
  max_concurrency_total?: number | null;
  allocation_ttl_seconds: number;
  cooldown_seconds: number;
  failure_cooldown_seconds: number;
  allow_attach_only: boolean;
  close_targets_on_release: boolean;
  close_targets_on_expire: boolean;
  health_policy?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  profile_count: number;
  eligible_profile_count: number;
  missing_profiles: string[];
  disabled_profiles: string[];
  attach_only_profiles: string[];
  ready: boolean;
}

export interface BrowserProfilePoolsApiPayload {
  default_profile: string;
  profile_count: number;
  pools: BrowserProfilePoolApiPayload[];
}

export interface BrowserProfileAllocationApiPayload {
  allocation_id: string;
  pool_id: string;
  profile_name: string;
  consumer_kind: string;
  consumer_id: string;
  target_host?: string | null;
  status: string;
  acquired_at: string;
  expires_at: string;
  released_at?: string | null;
  release_reason?: string | null;
  owned_target_ids?: string[];
  metadata?: Record<string, unknown>;
}

export interface BrowserProfilePoolDrainPayload {
  pool_id: string;
  released: number;
  allocations: BrowserProfileAllocationApiPayload[];
}

export interface BrowserProfileAllocationsApiPayload {
  total: number;
  allocations: BrowserProfileAllocationApiPayload[];
}

export async function listBrowserProfiles(): Promise<BrowserProfilesApiPayload> {
  return requestJson<BrowserProfilesApiPayload>("/browser/profiles");
}

export async function listBrowserProfilePools(): Promise<BrowserProfilePoolsApiPayload> {
  return requestJson<BrowserProfilePoolsApiPayload>("/browser/pools");
}

export async function listBrowserProfileAllocations(options: { activeOnly?: boolean } = {}): Promise<BrowserProfileAllocationsApiPayload> {
  const params = new URLSearchParams();
  if (options.activeOnly) params.set("active_only", "true");
  const suffix = params.toString();
  return requestJson<BrowserProfileAllocationsApiPayload>(`/browser/allocations${suffix ? `?${suffix}` : ""}`);
}

export async function setDefaultBrowserProfile(profileName: string): Promise<BrowserProfilesApiPayload> {
  return requestJson<BrowserProfilesApiPayload>("/browser/profiles/default", {
    method: "POST",
    body: JSON.stringify({ profile_name: profileName }),
  });
}

export interface BrowserProfileMutationPayload {
  name?: string;
  driver?: string;
  enabled?: boolean;
  cdp_url?: string | null;
  cdp_port?: number | null;
  user_data_dir?: string | null;
  profile_directory?: string | null;
  attach_only?: boolean;
  autostart?: boolean;
  proxy_mode?: string;
  proxy_server?: string | null;
  proxy_bypass_list?: string[];
  proxy_binding_id?: string | null;
  proxy_credential_kind?: string;
  close_targets_on_release?: boolean;
  close_targets_on_expire?: boolean;
  set_as_default?: boolean;
}

export interface BrowserProfilePoolMutationPayload {
  pool_id?: string;
  display_name?: string | null;
  enabled?: boolean;
  profile_names?: string[];
  target_hosts?: string[];
  selection_strategy?: string;
  max_concurrency_per_profile?: number;
  max_concurrency_total?: number | null;
  allocation_ttl_seconds?: number;
  cooldown_seconds?: number;
  failure_cooldown_seconds?: number;
  allow_attach_only?: boolean;
  close_targets_on_release?: boolean;
  close_targets_on_expire?: boolean;
  health_policy?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  clear_display_name?: boolean;
  clear_target_hosts?: boolean;
  clear_max_concurrency_total?: boolean;
  clear_health_policy?: boolean;
  clear_metadata?: boolean;
}

export interface BrowserProfileControlPayload {
  ok?: boolean;
  value?: Record<string, unknown>;
  message?: string | null;
}

export interface BrowserProfileTestPayload {
  enabled?: boolean;
  default_profile?: string;
  profile?: BrowserProfileApiPayload;
  status?: string;
  attempted?: boolean;
  proxy_mode?: string;
  result?: Record<string, unknown>;
  reason?: string;
}

export async function createBrowserProfile(payload: BrowserProfileMutationPayload): Promise<BrowserProfilesApiPayload> {
  return requestJson<BrowserProfilesApiPayload>("/browser/profiles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateBrowserProfile(profileName: string, payload: BrowserProfileMutationPayload): Promise<BrowserProfilesApiPayload> {
  return requestJson<BrowserProfilesApiPayload>(`/browser/profiles/${encodeURIComponent(profileName)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteBrowserProfile(profileName: string): Promise<BrowserProfilesApiPayload> {
  return requestJson<BrowserProfilesApiPayload>(`/browser/profiles/${encodeURIComponent(profileName)}`, {
    method: "DELETE",
  });
}

export async function setBrowserProfileEnabled(profileName: string, enabled: boolean): Promise<BrowserProfilesApiPayload> {
  return requestJson<BrowserProfilesApiPayload>(`/browser/profiles/${encodeURIComponent(profileName)}/${enabled ? "enable" : "disable"}`, {
    method: "POST",
  });
}

export async function controlBrowserProfile(profileName: string, action: "start" | "stop" | "restart"): Promise<BrowserProfileControlPayload> {
  return requestJson<BrowserProfileControlPayload>(`/browser/profiles/${encodeURIComponent(profileName)}/${action}`, {
    method: "POST",
  });
}

export async function testBrowserProfileCdp(profileName: string): Promise<BrowserProfileTestPayload> {
  return requestJson<BrowserProfileTestPayload>(`/browser/profiles/${encodeURIComponent(profileName)}/test-cdp`, {
    method: "POST",
  });
}

export async function testBrowserProfileEgress(profileName: string, url?: string): Promise<BrowserProfileTestPayload> {
  return requestJson<BrowserProfileTestPayload>(`/browser/profiles/${encodeURIComponent(profileName)}/test-egress`, {
    method: "POST",
    body: JSON.stringify(url ? { url } : {}),
  });
}

export async function createBrowserProfilePool(payload: BrowserProfilePoolMutationPayload): Promise<BrowserProfilePoolsApiPayload> {
  return requestJson<BrowserProfilePoolsApiPayload>("/browser/pools", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateBrowserProfilePool(poolId: string, payload: BrowserProfilePoolMutationPayload): Promise<BrowserProfilePoolsApiPayload> {
  return requestJson<BrowserProfilePoolsApiPayload>(`/browser/pools/${encodeURIComponent(poolId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteBrowserProfilePool(poolId: string): Promise<BrowserProfilePoolsApiPayload> {
  return requestJson<BrowserProfilePoolsApiPayload>(`/browser/pools/${encodeURIComponent(poolId)}`, {
    method: "DELETE",
  });
}

export async function setBrowserProfilePoolEnabled(poolId: string, enabled: boolean): Promise<BrowserProfilePoolsApiPayload> {
  return requestJson<BrowserProfilePoolsApiPayload>(`/browser/pools/${encodeURIComponent(poolId)}/${enabled ? "enable" : "disable"}`, {
    method: "POST",
  });
}

export async function drainBrowserProfilePool(poolId: string): Promise<BrowserProfilePoolDrainPayload> {
  return requestJson<BrowserProfilePoolDrainPayload>(`/browser/pools/${encodeURIComponent(poolId)}/drain`, {
    method: "POST",
  });
}

export async function releaseBrowserProfileAllocation(allocationId: string, reason = "settings-release"): Promise<{ allocation: BrowserProfileAllocationApiPayload }> {
  return requestJson<{ allocation: BrowserProfileAllocationApiPayload }>(`/browser/allocations/${encodeURIComponent(allocationId)}/release`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}
