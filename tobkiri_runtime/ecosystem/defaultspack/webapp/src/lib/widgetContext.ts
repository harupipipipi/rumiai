import { api, type Conversation } from "./api";

export type ConversationExportFormat = "markdown" | "json" | "text";

export type ConversationExport = {
  conversation_id: string;
  format: ConversationExportFormat;
  content: string;
};

export type WidgetConversationContext = {
  activeConversationId: string | null;
  fetchConversation: () => Promise<Conversation | null>;
  exportConversation: (format?: ConversationExportFormat) => Promise<ConversationExport | null>;
};

type WidgetConversationApi = {
  getConversation: (conversationId: string) => Promise<Conversation>;
  exportConversation: (
    conversationId: string,
    format: ConversationExportFormat,
  ) => Promise<ConversationExport>;
};

export function createWidgetConversationContext(
  activeConversationId: string | null,
  client: WidgetConversationApi = api,
): WidgetConversationContext {
  return {
    activeConversationId,
    fetchConversation: () => activeConversationId
      ? client.getConversation(activeConversationId)
      : Promise.resolve(null),
    exportConversation: (format = "json") => activeConversationId
      ? client.exportConversation(activeConversationId, format)
      : Promise.resolve(null),
  };
}
