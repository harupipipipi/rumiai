import type { DroppedWidget } from "../renderers/types";

export const HISTORY_CHAT_DROP_MIME = "application/rumi-history-chat";

export type HistoryChatDragPayload = {
  conversationId: string;
  title: string;
  conversationKind?: string;
  tags?: string[];
};

export function historyChatDragPayload(chat: {
  id: string;
  title: string;
  conversationKind?: string;
  tags?: string[];
}): HistoryChatDragPayload {
  return {
    conversationId: chat.id,
    title: chat.title,
    conversationKind: chat.conversationKind,
    tags: chat.tags ?? [],
  };
}

export function droppedWidgetFromHistoryChat(payload: HistoryChatDragPayload): DroppedWidget {
  return {
    id: `conversation:${payload.conversationId}`,
    type: "conversation",
    widgetKind: "history_context",
    sourceItemId: payload.conversationId,
    label: payload.title || payload.conversationId,
    description: "History chat context",
    enabled: true,
    metadata: {
      conversation_id: payload.conversationId,
      title: payload.title,
      conversation_kind: payload.conversationKind,
      tags: payload.tags ?? [],
    },
  };
}

export function parseHistoryChatDrop(raw: string): DroppedWidget | null {
  if (!raw.trim()) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<HistoryChatDragPayload>;
    const conversationId = String(parsed.conversationId ?? "").trim();
    if (!conversationId) return null;
    return droppedWidgetFromHistoryChat({
      conversationId,
      title: String(parsed.title ?? conversationId),
      conversationKind: typeof parsed.conversationKind === "string" ? parsed.conversationKind : undefined,
      tags: Array.isArray(parsed.tags) ? parsed.tags.map((tag) => String(tag)).filter(Boolean) : [],
    });
  } catch {
    return null;
  }
}
