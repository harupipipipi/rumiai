import type { Conversation, ConversationSearchResult } from "./api";
import { messageToText, orderConversationMessages } from "./chat";

export type SpotlightDateFilter = "all" | "today" | "7d" | "30d";
export type SpotlightFilter = SpotlightDateFilter | "starred";

export const SPOTLIGHT_FILTERS: Array<{ id: SpotlightFilter; labelKey: `spotlight.filter.${SpotlightFilter}`; hint: string }> = [
  { id: "all", labelKey: "spotlight.filter.all", hint: "すべて" },
  { id: "today", labelKey: "spotlight.filter.today", hint: "今日" },
  { id: "7d", labelKey: "spotlight.filter.7d", hint: "最近" },
  { id: "30d", labelKey: "spotlight.filter.30d", hint: "今月" },
  { id: "starred", labelKey: "spotlight.filter.starred", hint: "スター" },
];

export function conversationToSearchResult(conversation: Conversation): ConversationSearchResult {
  const latestText = messageToText(orderConversationMessages(conversation.messages).at(-1) ?? {
    id: "",
    role: "assistant",
    content: [],
    created_at: conversation.updated_at,
    conversation_id: conversation.id,
  });
  return {
    conversation_id: conversation.id,
    title: conversation.title || "New Conversation",
    created_at: conversation.created_at,
    updated_at: conversation.updated_at,
    is_starred: conversation.is_starred,
    is_archived: conversation.is_archived,
    match_count: conversation.messages.length,
    matches: latestText ? [{
      message_id: conversation.current_node_id ?? undefined,
      role: "latest",
      created_at: conversation.updated_at,
      snippet: latestText,
      exact: false,
      score: 0,
    }] : [],
  };
}

export function conversationMatchesSpotlightFilter(conversation: Conversation, filter: SpotlightFilter): boolean {
  if (filter === "starred") return Boolean(conversation.is_starred);
  if (filter === "all") return true;
  const dayMs = 86_400_000;
  const windowMs = filter === "today" ? dayMs : filter === "7d" ? dayMs * 7 : dayMs * 30;
  return Date.now() - Number(conversation.updated_at || 0) <= windowMs;
}
