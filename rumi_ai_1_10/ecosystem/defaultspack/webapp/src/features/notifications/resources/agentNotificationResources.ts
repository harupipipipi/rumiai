import { api, type ChatMessage, type Conversation } from "../../../lib/api";

export type { ChatMessage, Conversation };

export async function listAgentNotificationConversations(): Promise<Conversation[]> {
  const result = await api.listConversations({
    include_messages: true,
    is_archived: false,
    limit: 120,
  });
  return result.conversations;
}
