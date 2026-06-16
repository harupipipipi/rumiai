export type AmbientFinalAnswerPayload = {
  conversation_id: string | null;
  text: string;
  updated_at: number;
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
      text,
      updated_at: typeof parsed.updated_at === "number" ? parsed.updated_at : Date.now(),
    };
  } catch {
    return null;
  }
}

export function publishAmbientFinalAnswer(text: string, conversationId: string | null | undefined) {
  const trimmed = text.trim();
  if (!trimmed) return;
  const payload: AmbientFinalAnswerPayload = {
    conversation_id: conversationId ?? null,
    text: trimmed,
    updated_at: Date.now(),
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
