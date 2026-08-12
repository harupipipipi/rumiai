import type { ChatMessage } from "./api";

export type PendingChatRequest = {
  conversationId: string;
  operationId?: string;
  requestFingerprint?: string;
  startedAt: number;
  status: string;
  toolNames: string[];
  toolStartedAt?: Record<string, number>;
  recoveredFromLocation?: boolean;
};

export const PENDING_CHAT_REQUEST_TTL_MS = 6 * 60 * 60_000;
export const PENDING_USER_ONLY_GRACE_MS = 8_000;

export function shouldForgetPendingAfterPollError(errorValue: unknown): boolean {
  const message = errorValue instanceof Error ? errorValue.message : String(errorValue ?? "");
  return /(?:^|\n)HTTP (?:404|410)\b/i.test(message)
    || /\b(?:NOT_FOUND|EXPIRED)\b/i.test(message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function approvalCandidateRequiresUser(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return (
    value.requires_approval === true
    || value.approval_required === true
    || value.type === "approval_requested"
    || value.phase === "approval_requested"
  );
}

function messageHasPendingApproval(message: ChatMessage): boolean {
  const metadata = isRecord(message.metadata) ? message.metadata : {};
  if (
    isRecord(metadata.pendingApproval)
    || isRecord(metadata.pending_approval)
    || isRecord(metadata.pendingAuthorityApproval)
    || isRecord(metadata.pending_authority_approval)
  ) {
    return true;
  }

  for (const event of message.events ?? []) {
    if (approvalCandidateRequiresUser(event)) return true;
  }

  for (const log of message.tool_logs ?? []) {
    if (approvalCandidateRequiresUser(log)) return true;
    const result = isRecord(log.result) ? log.result : null;
    if (approvalCandidateRequiresUser(result)) return true;
    const data = isRecord(result?.data) ? result.data : result;
    if (approvalCandidateRequiresUser(data)) return true;
    const widget = isRecord(data?.widget) ? data.widget : null;
    if (approvalCandidateRequiresUser(widget)) return true;
  }

  return false;
}

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

export function pendingRequestBelongsToConversation(
  conversationId: string | null | undefined,
  request: PendingChatRequest | null | undefined,
): request is PendingChatRequest {
  const activeId = String(conversationId ?? "").trim();
  return Boolean(activeId && request && request.conversationId === activeId);
}

export function shouldKeepPendingAfterConversationRefresh(
  latest: ChatMessage | undefined,
  request: PendingChatRequest | null | undefined,
  now = Date.now(),
): boolean {
  if (!request || now - request.startedAt >= PENDING_CHAT_REQUEST_TTL_MS) return false;
  if (!latest) return Boolean(request.operationId);
  if (latest.conversation_id && latest.conversation_id !== request.conversationId) return false;
  if (messageHasPendingApproval(latest)) return false;
  if (latest.role !== "user") return isAssistantMessageStillRunning(latest);
  if (request.operationId) return true;
  return now - request.startedAt < PENDING_USER_ONLY_GRACE_MS;
}

export function shouldClearPendingAfterConversationRefresh(
  latest: ChatMessage | undefined,
  request: PendingChatRequest | null | undefined,
  now = Date.now(),
): boolean {
  if (!request) return false;
  return !shouldKeepPendingAfterConversationRefresh(latest, request, now);
}
