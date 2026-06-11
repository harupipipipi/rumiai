import { api, type SystemPromptListResponse, type SystemPromptRecord } from "../../../lib/api";

export type { SystemPromptListResponse, SystemPromptRecord };

export type SystemPromptSavePayload = Partial<SystemPromptRecord> & {
  activate?: boolean;
};

export const systemPromptResources = {
  list() {
    return api.listSystemPrompts();
  },

  create(payload: SystemPromptSavePayload) {
    return api.createSystemPrompt(payload);
  },

  update(promptId: string, updates: SystemPromptSavePayload) {
    return api.updateSystemPrompt(promptId, updates);
  },

  remove(promptId: string) {
    return api.deleteSystemPrompt(promptId);
  },

  activate(promptId: string) {
    return api.activateSystemPrompt(promptId);
  },
};
