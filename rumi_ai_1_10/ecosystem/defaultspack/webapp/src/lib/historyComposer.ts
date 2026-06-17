import type { DroppedWidget } from "../renderers/types";

export const HISTORY_CHAT_DROP_MIME = "application/rumi-history-chat";
export const HISTORY_CHAT_KANBAN_DROP_EVENT = "rumi:history-chat-kanban-drop";

export type HistoryChatDragPayload = {
  conversationId: string;
  title: string;
  conversationKind?: string;
  groupId?: string;
  tags?: string[];
};

export function historyChatDragPayload(chat: {
  id: string;
  title: string;
  conversationKind?: string;
  groupId?: string;
  tags?: string[];
}): HistoryChatDragPayload {
  return {
    conversationId: chat.id,
    title: chat.title,
    conversationKind: chat.conversationKind,
    groupId: chat.groupId,
    tags: chat.tags ?? [],
  };
}

export function droppedWidgetFromHistoryChat(payload: HistoryChatDragPayload): DroppedWidget {
  const metadata: Record<string, unknown> = {
    conversation_id: payload.conversationId,
    title: payload.title,
    conversation_kind: payload.conversationKind,
    tags: payload.tags ?? [],
  };
  if (payload.groupId) metadata.group_id = payload.groupId;
  return {
    id: `conversation:${payload.conversationId}`,
    type: "conversation",
    widgetKind: "history_context",
    sourceItemId: payload.conversationId,
    label: payload.title || payload.conversationId,
    description: "History chat context",
    enabled: true,
    metadata,
  };
}

export function parseHistoryChatDragPayload(raw: string): HistoryChatDragPayload | null {
  if (!raw.trim()) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<HistoryChatDragPayload>;
    const conversationId = String(parsed.conversationId ?? "").trim();
    if (!conversationId) return null;
    return {
      conversationId,
      title: String(parsed.title ?? conversationId),
      conversationKind: typeof parsed.conversationKind === "string" ? parsed.conversationKind : undefined,
      groupId: typeof parsed.groupId === "string" ? parsed.groupId : undefined,
      tags: Array.isArray(parsed.tags) ? parsed.tags.map((tag) => String(tag)).filter(Boolean) : [],
    };
  } catch {
    return null;
  }
}

export function parseHistoryChatDrop(raw: string): DroppedWidget | null {
  const payload = parseHistoryChatDragPayload(raw);
  return payload ? droppedWidgetFromHistoryChat(payload) : null;
}
