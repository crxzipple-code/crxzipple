import { requestJson } from "@/shared/api/client";

export type ChannelOwnerJsonRecord = Record<string, unknown>;

export interface ChannelProfileApiPayload {
  channel_type: string;
  enabled: boolean;
  capabilities: ChannelOwnerJsonRecord;
  accounts: ChannelOwnerJsonRecord[];
  metadata: ChannelOwnerJsonRecord;
}

export interface ChannelProfileWritePayload {
  channel_type?: string | null;
  enabled: boolean;
  capabilities?: ChannelOwnerJsonRecord;
  accounts?: ChannelOwnerJsonRecord[];
  metadata?: ChannelOwnerJsonRecord;
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
