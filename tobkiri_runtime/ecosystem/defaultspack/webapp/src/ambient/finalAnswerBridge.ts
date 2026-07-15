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

export type AmbientFinalAnswerReference = {
  schema_version: 1;
  kind: "ambient_final_answer_ref";
  conversation_id: string;
  message_id: string;
  message_created_at: number | null;
  updated_at: number;
  expires_at: number;
  nonce: string;
};

export const AMBIENT_FINAL_ANSWER_CHANNEL = "rumi.ambient.finalAnswer.v2";
export const LEGACY_AMBIENT_FINAL_ANSWER_STORAGE_KEY = "rumi.ambient.latestFinalAnswer";
export const AMBIENT_FINAL_ANSWER_REFERENCE_TTL_MS = 30_000;

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

export function parseAmbientFinalAnswerReference(
  raw: unknown,
  now = Date.now(),
): AmbientFinalAnswerReference | null {
  try {
    const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    const record = parsed as Record<string, unknown>;
    if (record.kind !== "ambient_final_answer_ref" || Number(record.schema_version) !== 1) return null;
    if (Object.prototype.hasOwnProperty.call(record, "text")) return null;

    const conversationId = cleanString(record.conversation_id);
    const messageId = cleanString(record.message_id);
    const nonce = cleanString(record.nonce);
    const updatedAt = finiteNumberOrNull(record.updated_at);
    const expiresAt = finiteNumberOrNull(record.expires_at);
    if (!conversationId || !messageId || !nonce || updatedAt === null || expiresAt === null) return null;
    if (expiresAt < now || expiresAt > now + AMBIENT_FINAL_ANSWER_REFERENCE_TTL_MS * 2) return null;

    return {
      schema_version: 1,
      kind: "ambient_final_answer_ref",
      conversation_id: conversationId,
      message_id: messageId,
      message_created_at: finiteNumberOrNull(record.message_created_at),
      updated_at: updatedAt,
      expires_at: expiresAt,
      nonce,
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

export function createAmbientFinalAnswerReference(
  input: AmbientFinalAnswerInput,
  now = Date.now(),
): AmbientFinalAnswerReference | null {
  const conversationId = cleanString(input.conversationId);
  const messageId = cleanString(input.messageId);
  if (!conversationId || !messageId) return null;
  const updatedAt = finiteNumberOrNull(input.updatedAt) ?? now;
  return {
    schema_version: 1,
    kind: "ambient_final_answer_ref",
    conversation_id: conversationId,
    message_id: messageId,
    message_created_at: finiteNumberOrNull(input.messageCreatedAt),
    updated_at: updatedAt,
    expires_at: now + AMBIENT_FINAL_ANSWER_REFERENCE_TTL_MS,
    nonce: createReferenceNonce(),
  };
}

export function publishAmbientFinalAnswer(
  text: string,
  conversationId: string | null | undefined,
  options?: { messageId?: string | null; messageCreatedAt?: number | null; updatedAt?: number },
): AmbientFinalAnswerReference | null {
  return publishAmbientFinalAnswerPayload({
    conversationId,
    messageId: options?.messageId,
    messageCreatedAt: options?.messageCreatedAt,
    text,
    updatedAt: options?.updatedAt,
  });
}

export function publishAmbientFinalAnswerPayload(input: AmbientFinalAnswerInput): AmbientFinalAnswerReference | null {
  if (!input.text.trim()) return null;
  const reference = createAmbientFinalAnswerReference(input);
  if (!reference) return null;
  try {
    const channel = new BroadcastChannel(AMBIENT_FINAL_ANSWER_CHANNEL);
    channel.postMessage(reference);
    channel.close();
  } catch {
    // Reference delivery is optional. Full answer content is never persisted or broadcast as fallback.
  }
  return reference;
}

function createReferenceNonce(): string {
  try {
    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
  }
}

function cleanString(value: unknown): string | null {
  const text = String(value ?? "").trim();
  return text || null;
}

function finiteNumberOrNull(value: unknown): number | null {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}
