import type { Conversation } from "../lib/api";
import { ambientLatestAssistantFinal, ambientPendingAuthorityApproval, type AmbientAssistantFinal } from "./ambientMiniChatState";

export type AmbientConversationCompletion = {
  status: "waiting" | "completed" | "approval_required" | "timeout";
  conversation: Conversation | null;
  assistant: AmbientAssistantFinal | null;
};

export function ambientConversationCompletionFromSnapshot({
  conversation,
  previousAssistantMessageId,
  submittedAt,
}: {
  conversation: Conversation | null | undefined;
  previousAssistantMessageId?: string | null;
  submittedAt: number;
}): AmbientConversationCompletion {
  const snapshot = conversation ?? null;
  if (ambientPendingAuthorityApproval(snapshot)) {
    return { status: "approval_required", conversation: snapshot, assistant: null };
  }
  const assistant = ambientLatestAssistantFinal(snapshot);
  const isNewMessage = Boolean(assistant && assistant.messageId !== String(previousAssistantMessageId ?? ""));
  const isAfterSubmission = Boolean(assistant && (!assistant.createdAt || assistant.createdAt >= submittedAt - 2_000));
  if (assistant && isNewMessage && isAfterSubmission) {
    return { status: "completed", conversation: snapshot, assistant };
  }
  return { status: "waiting", conversation: snapshot, assistant: null };
}

export async function waitForAmbientAssistantResponse({
  conversationId,
  previousAssistantMessageId,
  submittedAt,
  fetchConversation,
  timeoutMs = 30_000,
  pollIntervalMs = 500,
  sleep = delay,
}: {
  conversationId: string;
  previousAssistantMessageId?: string | null;
  submittedAt: number;
  fetchConversation: (conversationId: string) => Promise<Conversation>;
  timeoutMs?: number;
  pollIntervalMs?: number;
  sleep?: (durationMs: number) => Promise<void>;
}): Promise<AmbientConversationCompletion> {
  const deadline = Date.now() + Math.max(0, timeoutMs);
  let latest: Conversation | null = null;
  do {
    latest = await fetchConversation(conversationId);
    const outcome = ambientConversationCompletionFromSnapshot({
      conversation: latest,
      previousAssistantMessageId,
      submittedAt,
    });
    if (outcome.status !== "waiting") return outcome;
    if (Date.now() >= deadline) break;
    await sleep(Math.max(0, pollIntervalMs));
  } while (Date.now() <= deadline);
  return { status: "timeout", conversation: latest, assistant: null };
}

function delay(durationMs: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, durationMs));
}
