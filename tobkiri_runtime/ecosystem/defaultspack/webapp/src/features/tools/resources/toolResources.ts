import { api } from "../../../lib/api";
import type { ModelSearchResponse, ToolCatalogResponse, ToolSelectionPreviewResponse, ToolSelectionRequest } from "../../../lib/api";

export const toolResources = {
  toolCatalog(): Promise<ToolCatalogResponse> {
    return api.toolCatalog();
  },

  searchModels(filters: Record<string, unknown>): Promise<ModelSearchResponse> {
    return api.searchModels(filters);
  },

  previewToolSelection(payload: {
    conversation_id?: string | null;
    user_text?: string;
    text?: string;
    attachment_metadata?: unknown[];
    tool_selection?: ToolSelectionRequest;
    model?: string | null;
  }): Promise<ToolSelectionPreviewResponse> {
    return api.previewToolSelection(payload);
  },

  getConversationToolPreferences(conversationId: string): Promise<{ conversation_id: string; preferences: Record<string, unknown> }> {
    return api.getConversationToolPreferences(conversationId);
  },

  updateConversationToolPreferences(conversationId: string, preferences: Record<string, unknown>): Promise<{ conversation_id: string; preferences: Record<string, unknown> }> {
    return api.updateConversationToolPreferences(conversationId, preferences);
  },
};
