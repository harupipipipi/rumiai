import { api, type PromptUsageSummary } from "../../../lib/api";

type PromptActiveParams = {
  profile_id?: string;
  conversation_id?: string;
  include_text?: boolean;
};

type PromptTogglePayload = {
  profile_id?: string;
  conversation_id?: string;
  edge_id: string;
  enabled: boolean;
};

export const promptResources = {
  async getActiveSummary(params: PromptActiveParams): Promise<PromptUsageSummary> {
    const result = await api.getPromptActive(params);
    return result.summary;
  },

  async toggleEdge(payload: PromptTogglePayload): Promise<PromptUsageSummary> {
    const result = await api.togglePromptEdge(payload);
    return result.summary;
  },

  async getTraceUsage(traceId: string, profileId?: string): Promise<PromptUsageSummary> {
    const result = await api.getPromptTrace(traceId, { profile_id: profileId || undefined, include_text: true });
    return result.prompt_usage;
  },
};

export type { PromptActiveParams, PromptTogglePayload };
