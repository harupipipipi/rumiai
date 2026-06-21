export type AmbientFinalAnswerPayload = {
  conversation_id: string | null;
  message_id: string | null;
  message_created_at: number | null;
  text: string;
  updated_at: number;
};

export type AmbientFinalAnswerInput = {
  conversationId?: string | null;
  messageId?: string | null;
  messageCreatedAt?: number | null;
  text: string;
  updatedAt?: number;
};

export const AMBIENT_FINAL_ANSWER_CHANNEL = "rumi.ambient.finalAnswer";
export const AMBIENT_FINAL_ANSWER_STORAGE_KEY = "rumi.ambient.latestFinalAnswer";

export function parseAmbientFinalAnswerPayload(raw: string | null | undefined): AmbientFinalAnswerPayload | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<AmbientFinalAnswerPayload>;
    const text = typeof parsed.text === "string" ? parsed.text.trim() : "";
    if (!text) return null;
    return {
      conversation_id: typeof parsed.conversation_id === "string" ? parsed.conversation_id : null,
      message_id: typeof parsed.message_id === "string" ? parsed.message_id : null,
      message_created_at: finiteNumberOrNull(parsed.message_created_at),
      text,
      updated_at: finiteNumberOrNull(parsed.updated_at) ?? Date.now(),
    };
  } catch {
    return null;
  }
}

export function ambientFinalAnswerKey(payload: AmbientFinalAnswerPayload): string {
  const conversation = payload.conversation_id ?? "";
  if (payload.message_id) return `${conversation}:${payload.message_id}`;
  return `${conversation}:${payload.message_created_at ?? payload.updated_at}:${payload.text}`;
}

export function publishAmbientFinalAnswer(
  text: string,
  conversationId: string | null | undefined,
  options?: { messageId?: string | null; messageCreatedAt?: number | null; updatedAt?: number },
) {
  publishAmbientFinalAnswerPayload({
    conversationId,
    messageId: options?.messageId,
    messageCreatedAt: options?.messageCreatedAt,
    text,
    updatedAt: options?.updatedAt,
  });
}

export function publishAmbientFinalAnswerPayload(input: AmbientFinalAnswerInput) {
  const trimmed = input.text.trim();
  if (!trimmed) return;
  const payload: AmbientFinalAnswerPayload = {
    conversation_id: input.conversationId ?? null,
    message_id: input.messageId ?? null,
    message_created_at: finiteNumberOrNull(input.messageCreatedAt),
    text: trimmed,
    updated_at: input.updatedAt ?? Date.now(),
  };
  const serialized = JSON.stringify(payload);
  try {
    window.localStorage.setItem(AMBIENT_FINAL_ANSWER_STORAGE_KEY, serialized);
  } catch {
    // Local storage can be disabled in browser tests; the BroadcastChannel path is enough there.
  }
  try {
    const channel = new BroadcastChannel(AMBIENT_FINAL_ANSWER_CHANNEL);
    channel.postMessage(payload);
    channel.close();
  } catch {
    // BroadcastChannel is not available in every embedded browser.
  }
}

function finiteNumberOrNull(value: unknown): number | null {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}
