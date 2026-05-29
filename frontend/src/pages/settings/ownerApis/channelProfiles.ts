import { requestJson } from "@/shared/api/client";

export type ChannelOwnerJsonRecord = Record<string, unknown>;

export interface ChannelCredentialSlotPayload {
  slot?: string;
  expected_kind?: string;
  binding_id?: string | null;
  required?: boolean;
  display_name?: string | null;
  scopes?: string[];
  metadata?: ChannelOwnerJsonRecord;
}

export interface ChannelCredentialRequirementPayload {
  requirement_id?: string;
  consumer?: ChannelOwnerJsonRecord;
  slot?: ChannelCredentialSlotPayload;
  provider?: string | null;
  transport?: string;
  parameter_name?: string | null;
  setup_flow_hint?: ChannelOwnerJsonRecord;
  metadata?: ChannelOwnerJsonRecord;
}

export interface ChannelCredentialRequirementSetPayload {
  requirement_set_id?: string;
  consumer?: ChannelOwnerJsonRecord;
  alternative?: boolean;
  metadata?: ChannelOwnerJsonRecord;
  requirements?: ChannelCredentialRequirementPayload[];
}

export interface ChannelAccountPayload {
  account_id?: string;
  enabled?: boolean;
  transport_mode?: string;
  credential_bindings?: Record<string, string>;
  credential_requirements?: ChannelCredentialRequirementSetPayload | null;
  metadata?: ChannelOwnerJsonRecord;
}

export interface ChannelProfileApiPayload {
  channel_type: string;
  enabled: boolean;
  capabilities: ChannelOwnerJsonRecord;
  accounts: ChannelAccountPayload[];
  metadata: ChannelOwnerJsonRecord;
}

export interface ChannelProfileWritePayload {
  channel_type?: string | null;
  enabled: boolean;
  capabilities?: ChannelOwnerJsonRecord;
  accounts?: ChannelAccountPayload[];
  metadata?: ChannelOwnerJsonRecord;
}

export interface AccessCredentialBindingPayload {
  binding_id: string;
  binding_kind?: string;
  source_kind?: string;
  asset_id?: string | null;
  masked_preview?: string | null;
  status?: string;
  metadata?: ChannelOwnerJsonRecord;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AccessCredentialRequirementPayload {
  requirement_id: string;
  consumer_module?: string;
  consumer_kind?: string;
  consumer_id?: string;
  slot?: string;
  expected_kind?: string;
  binding_id?: string | null;
  consumer_binding_id?: string | null;
  display_name?: string | null;
  provider?: string | null;
  required?: boolean;
  ready?: boolean;
  missing?: boolean;
  status?: string;
  reason?: string | null;
  setup_flow_hint?: ChannelOwnerJsonRecord | null;
  metadata?: ChannelOwnerJsonRecord;
  last_checked_at?: string | null;
}

export interface AccessOverviewPayload {
  ready?: boolean;
  counts?: ChannelOwnerJsonRecord;
  credential_requirements?: AccessCredentialRequirementPayload[];
  credential_bindings?: AccessCredentialBindingPayload[];
  degraded?: boolean;
  degraded_reason?: string | null;
  dependency_missing?: string[];
  generated_at?: string | null;
}

export function listChannelProfiles(): Promise<ChannelProfileApiPayload[]> {
  return requestJson<ChannelProfileApiPayload[]>("/channels/profiles");
}

export function getChannelProfile(channelType: string): Promise<ChannelProfileApiPayload> {
  return requestJson<ChannelProfileApiPayload>(
    `/channels/profiles/${encodeURIComponent(channelType)}`,
  );
}

export function upsertChannelProfile(
  channelType: string,
  payload: ChannelProfileWritePayload,
): Promise<ChannelProfileApiPayload> {
  return requestJson<ChannelProfileApiPayload>(
    `/channels/profiles/${encodeURIComponent(channelType)}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export function setChannelProfileEnabled(
  channelType: string,
  enabled: boolean,
): Promise<ChannelProfileApiPayload> {
  return requestJson<ChannelProfileApiPayload>(
    `/channels/profiles/${encodeURIComponent(channelType)}/${enabled ? "enable" : "disable"}`,
    { method: "POST" },
  );
}

export function deleteChannelProfile(channelType: string): Promise<ChannelProfileApiPayload[]> {
  return requestJson<ChannelProfileApiPayload[]>(
    `/channels/profiles/${encodeURIComponent(channelType)}`,
    { method: "DELETE" },
  );
}

export function getAccessOverviewForChannelSettings(): Promise<AccessOverviewPayload> {
  return requestJson<AccessOverviewPayload>("/ui/access");
}
