import type { ChatMessage } from "./api";

export type PendingChatRequest = {
  conversationId: string;
  startedAt: number;
  status: string;
  toolNames: string[];
  recoveredFromLocation?: boolean;
};

export const PENDING_CHAT_REQUEST_TTL_MS = 6 * 60 * 60_000;
export const PENDING_USER_ONLY_GRACE_MS = 8_000;

export function isAssistantMessageStillRunning(message: ChatMessage | undefined): boolean {
  if (!message || message.role === "user") return false;
  const metadata = message.metadata && typeof message.metadata === "object" ? message.metadata : {};
  const thinking = metadata.thinking && typeof metadata.thinking === "object"
    ? metadata.thinking as Record<string, unknown>
    : {};
  const state = String(thinking.state ?? "").toLowerCase();
  const finishReason = String(message.finish_reason ?? "").toLowerCase();
  return state === "streaming" || state === "running" || finishReason === "streaming";
}

export function shouldClearPendingAfterConversationRefresh(
  latest: ChatMessage | undefined,
  request: PendingChatRequest | null | undefined,
  now = Date.now(),
): boolean {
  if (!latest || !request) return false;
  if (latest.role !== "user") return !isAssistantMessageStillRunning(latest);
  return now - request.startedAt >= PENDING_USER_ONLY_GRACE_MS;
}
