import type { ChatItem } from "../components/HistoryBoard";
import type { Conversation, ModelSearchItem } from "../lib/api";
import { formatRelativeTime } from "../lib/chat";
import type { AmbientRoutingConfig, AmbientRoutingMode } from "./ambientTriggerClient";

export type NormalizedAmbientRouting = {
  mode: AmbientRoutingMode;
  conversation_id: string | null;
  group_enabled: boolean;
  group_id: string;
  group_title: string;
  model: string;
  ai_send_approval_required: boolean;
};

export function normalizeRouting(value: AmbientRoutingConfig | null | undefined, fallbackConversationId: string | null): NormalizedAmbientRouting {
  const mode = value?.mode === "startup_new_chat" || value?.mode === "always_new_chat" || value?.mode === "selected_chat"
    ? value.mode
    : "selected_chat";
  return {
    mode,
    conversation_id: cleanOptionalText(value?.conversation_id) ?? fallbackConversationId,
    group_enabled: cleanBool(value?.group_enabled, true),
    group_id: cleanOptionalText(value?.group_id) ?? "gesture",
    group_title: cleanOptionalText(value?.group_title) ?? "Gesture",
    model: cleanOptionalText(value?.model) ?? "",
    ai_send_approval_required: cleanBool(value?.ai_send_approval_required, false),
  };
}

export function conversationsToChatItems(conversations: Conversation[]): ChatItem[] {
  const byId = new Map(conversations.map((conversation) => [conversation.id, conversation]));
  const build = (conversation: Conversation): ChatItem => ({
    id: conversation.id,
    title: conversation.title || "New Conversation",
    date: formatRelativeTime(conversation.updated_at || conversation.created_at || Date.now()),
    type: "chat",
    parentId: conversation.parent_conversation_id ?? null,
    conversationKind: conversation.conversation_kind,
    tags: conversation.tags ?? [],
    isStarred: Boolean(conversation.is_starred),
    isPinned: Boolean(conversation.is_pinned),
    companyId: cleanOptionalText(conversation.metadata?.company_id ?? conversation.metadata?.companyId),
    workspaceId: cleanOptionalText(conversation.metadata?.workspace_id ?? conversation.metadata?.workspaceId),
    metadata: conversation.metadata ?? {},
    children: (conversation.child_conversation_ids ?? [])
      .map((id) => byId.get(id))
      .filter((item): item is Conversation => Boolean(item))
      .map(build),
  });
  const childIds = new Set(conversations.flatMap((conversation) => conversation.child_conversation_ids ?? []));
  return conversations.filter((conversation) => !childIds.has(conversation.id)).map(build);
}

export function routingLabel(
  mode: AmbientRoutingMode,
  conversation: Conversation | null,
  conversationId: string | null,
  sessionConversationId: string | null | undefined,
): string {
  if (mode === "selected_chat") {
    return conversation?.title || (conversationId ? "選択済み" : "未選択");
  }
  if (mode === "startup_new_chat") {
    return sessionConversationId ? "この起動のチャット" : "起動ごとに新規";
  }
  return "毎回新しいチャット";
}

export function modelIdForSearchItem(item: ModelSearchItem): string {
  return String(item.profile_id || item.qualified_model_id || item.model_id || item.display_name || item.label || "").trim();
}

export function modelLabelForSearchItem(item: ModelSearchItem): string {
  const id = modelIdForSearchItem(item);
  const label = String(item.display_name || item.label || id).trim();
  const provider = String(item.provider_display_name || item.provider_id || "").trim();
  return provider && !label.includes(provider) ? `${label} · ${provider}` : label;
}

export function modelLabelFromId(value: string): string {
  const text = value.trim();
  if (!text) return "未指定";
  const withoutProviderPrefix = text.includes("/") ? text.split("/").slice(1).join("/") : text;
  return withoutProviderPrefix || text;
}

function cleanOptionalText(value: unknown): string | null {
  const text = String(value ?? "").trim();
  return text || null;
}

function cleanBool(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["1", "true", "yes", "on"].includes(normalized)) return true;
    if (["0", "false", "no", "off"].includes(normalized)) return false;
  }
  return fallback;
}
