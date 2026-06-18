import type { ChatMessage, Conversation } from "../lib/api";
import { messageToText, orderConversationMessages } from "../lib/chat";
import type { AmbientStatus } from "./ambientTriggerClient";

export type AmbientMiniChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: number;
};

export function ambientLinkedConversationId(status: AmbientStatus | null, fallbackConversationId?: string | null): string | null {
  const routing = status?.routing;
  const fallback = cleanString(fallbackConversationId);
  if (!routing) return fallback;

  const mode = String(routing.mode || "selected_chat");
  if (mode === "startup_new_chat") {
    return cleanString(routing.session_conversation_id) || null;
  }
  if (mode === "always_new_chat") {
    return null;
  }
  return cleanString(routing.conversation_id) || fallback;
}

export function ambientConversationIdFromResult(result: Record<string, unknown> | null | undefined): string | null {
  if (!result) return null;
  return (
    cleanString(result.conversation_id)
    || cleanString(recordValue(result.dispatch)?.conversation_id)
    || cleanString(recordValue(result.dispatch_result)?.conversation_id)
    || cleanString(recordValue(result.pending_approval)?.conversation_id)
    || null
  );
}

export function ambientMiniChatMessages(conversation: Conversation | null | undefined, limit = 6): AmbientMiniChatMessage[] {
  if (!conversation) return [];
  const messages = orderConversationMessages(conversation.messages ?? [])
    .map(miniChatMessageFromChatMessage)
    .filter((message): message is AmbientMiniChatMessage => Boolean(message));
  return messages.slice(-Math.max(1, limit));
}

function miniChatMessageFromChatMessage(message: ChatMessage): AmbientMiniChatMessage | null {
  const role = String(message.role || "").toLowerCase();
  if (role !== "user" && role !== "assistant" && role !== "agent") return null;
  const text = messageToText(message).trim();
  const streaming = Boolean(message.metadata && typeof message.metadata === "object" && message.metadata.streaming);
  if (!text && !streaming) return null;
  return {
    id: String(message.id || `${role}-${message.created_at}`),
    role: role === "user" ? "user" : "assistant",
    text: text || "...",
    createdAt: Number(message.created_at) || 0,
  };
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function cleanString(value: unknown): string | null {
  const text = String(value ?? "").trim();
  return text || null;
}
