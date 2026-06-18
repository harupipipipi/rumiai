import type { ChatMessage, Conversation } from "../lib/api";
import {
  AUTHORITY_FOLLOWUP_TEXT,
  AUTHORITY_WAITING_TEXT,
  authorityApprovalFromRecord,
  pendingAuthorityApproval,
  sanitizeAssistantAuthorityBoilerplate,
  type AuthorityApproval,
} from "../lib/authorityApproval";
import { messageToText, orderConversationMessages } from "../lib/chat";
import type { ChatUiMessage } from "../renderers/types";
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

export function ambientPendingAuthorityApproval(conversation: Conversation | null | undefined): AuthorityApproval | null {
  if (!conversation) return null;
  return pendingAuthorityApproval(chatUiMessagesFromConversation(conversation));
}

export function ambientLatestAssistantFinalText(conversation: Conversation | null | undefined): string | null {
  if (!conversation) return null;
  for (const message of [...orderConversationMessages(conversation.messages ?? [])].reverse()) {
    const role = normalizedMessageRole(message);
    if (role === "user") return null;
    if (role !== "assistant") continue;

    const rawText = messageToText(message).trim();
    if (!rawText) continue;
    if (isAuthorityWaitingChatMessage(message, rawText)) return null;
    const text = sanitizeAssistantAuthorityBoilerplate(rawText).trim();
    if (text) return text;
  }
  return null;
}

function miniChatMessageFromChatMessage(message: ChatMessage): AmbientMiniChatMessage | null {
  if (isHiddenAuthorityFollowupChatMessage(message)) return null;
  const role = normalizedMessageRole(message);
  if (role !== "user" && role !== "assistant") return null;
  const rawText = messageToText(message).trim();
  if (isAuthorityWaitingChatMessage(message, rawText)) return null;
  const text = role === "assistant"
    ? sanitizeAssistantAuthorityBoilerplate(rawText).trim()
    : rawText;
  const metadata = recordValue(message.metadata);
  const streaming = Boolean(metadata?.streaming);
  if (!text && !streaming) return null;
  return {
    id: String(message.id || `${role}-${message.created_at}`),
    role,
    text: text || "...",
    createdAt: Number(message.created_at) || 0,
  };
}

function chatUiMessagesFromConversation(conversation: Conversation): ChatUiMessage[] {
  return orderConversationMessages(conversation.messages ?? [])
    .map(chatUiMessageFromChatMessage)
    .filter((message): message is ChatUiMessage => Boolean(message));
}

function chatUiMessageFromChatMessage(message: ChatMessage): ChatUiMessage | null {
  const role = normalizedMessageRole(message);
  if (role !== "user" && role !== "assistant") return null;
  const metadata = recordValue(message.metadata);
  const pendingAuthority = recordValue(metadata?.pendingAuthorityApproval ?? metadata?.pending_authority_approval);
  const authorityFollowup = recordValue(metadata?.authorityFollowup ?? metadata?.authority_followup);
  const chatDisplay = recordValue(metadata?.chatDisplay ?? metadata?.chat_display);
  const uiMetadata: ChatUiMessage["metadata"] = {
    ...(pendingAuthority ? { pendingAuthorityApproval: pendingAuthority } : {}),
    ...(authorityFollowup ? { authorityFollowup } : {}),
    ...(chatDisplay ? { chatDisplay } : {}),
  };
  return {
    id: String(message.id || `${role}-${message.created_at}`),
    conversationId: message.conversation_id,
    createdAt: message.created_at,
    role: role === "user" ? "user" : "agent",
    content: typeof message.content === "string" ? [{ type: "text", text: message.content }] : message.content,
    rawText: messageToText(message),
    widget: message.widget,
    events: message.events ?? [],
    toolLogs: message.tool_logs ?? [],
    metadata: Object.keys(uiMetadata).length > 0 ? uiMetadata : undefined,
  };
}

function authorityApprovalForChatMessage(message: ChatMessage): AuthorityApproval | null {
  const metadata = recordValue(message.metadata);
  const metadataApproval = authorityApprovalFromRecord(
    metadata?.pendingAuthorityApproval ?? metadata?.pending_authority_approval,
    { assumeAuthority: true },
  );
  if (metadataApproval) return metadataApproval;

  for (const event of [...(message.events ?? [])].reverse()) {
    if (event.type !== "approval_requested" && event.phase !== "approval_requested") continue;
    const approval = authorityApprovalFromRecord(event);
    if (approval) return approval;
  }
  return null;
}

function isAuthorityWaitingChatMessage(message: ChatMessage, rawText: string): boolean {
  return normalizedMessageRole(message) === "assistant"
    && rawText === AUTHORITY_WAITING_TEXT
    && Boolean(authorityApprovalForChatMessage(message));
}

function isHiddenAuthorityFollowupChatMessage(message: ChatMessage): boolean {
  if (normalizedMessageRole(message) !== "user") return false;
  const metadata = recordValue(message.metadata);
  const followup = recordValue(metadata?.authority_followup ?? metadata?.authorityFollowup);
  const chatDisplay = recordValue(metadata?.chat_display ?? metadata?.chatDisplay);
  const requestId = cleanString(followup?.request_id ?? followup?.approval_request_id);
  const permissionId = cleanString(followup?.permission_id);
  const hasAuthorityMarker = Boolean(requestId && permissionId);
  if (chatDisplay?.hidden === true && chatDisplay.reason === "authority_followup" && hasAuthorityMarker) return true;
  return messageToText(message).trim() === AUTHORITY_FOLLOWUP_TEXT && hasAuthorityMarker;
}

function normalizedMessageRole(message: ChatMessage): "user" | "assistant" | null {
  const role = String(message.role || "").toLowerCase();
  if (role === "user") return "user";
  if (role === "assistant" || role === "agent") return "assistant";
  return null;
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function cleanString(value: unknown): string | null {
  const text = String(value ?? "").trim();
  return text || null;
}
