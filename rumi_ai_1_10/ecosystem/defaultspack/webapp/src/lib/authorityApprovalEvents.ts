import type { AuthorityRequest } from "./api";

const AUTHORITY_APPROVAL_CHANNEL = "rumi-authority-approval";
const AUTHORITY_APPROVAL_MESSAGE_TYPE = "rumi-authority-approval-settlement-hint";
const LEGACY_AUTHORITY_APPROVAL_MESSAGE_TYPE = "rumi-authority-approval-settlement";
const LEGACY_AUTHORITY_APPROVAL_STORAGE_KEY = "rumi.authority.approval.settlement";
const AUTHORITY_APPROVAL_HINT_MAX_AGE_MS = 60 * 1000;
const AUTHORITY_APPROVAL_LOOKUP_WINDOW_MS = 10 * 1000;
const AUTHORITY_APPROVAL_LOOKUP_LIMIT = 12;

export type AuthorityApprovalSettlement = {
  requestId: string;
  status: "approved" | "denied";
  conversationId?: string | null;
};

export type AuthorityApprovalHint = {
  requestId: string;
  conversationId?: string | null;
  issuedAt?: number;
  nonce?: string;
};

export type AuthorityApprovalVerificationReason =
  | "malformed_hint"
  | "stale_hint"
  | "unexpected_request"
  | "lookup_failed"
  | "request_mismatch"
  | "conversation_mismatch"
  | "principal_mismatch"
  | "permission_mismatch"
  | "request_not_settled";

export type AuthorityApprovalVerificationResult =
  | {
      kind: "verified";
      settlement: AuthorityApprovalSettlement;
      request: AuthorityRequest;
    }
  | {
      kind: "ignored";
      reason: AuthorityApprovalVerificationReason;
    };

export type AuthorityApprovalVerificationState =
  | { kind: "verifying"; requestId: string }
  | { kind: "verified"; settlement: AuthorityApprovalSettlement }
  | { kind: "ignored"; requestId: string; reason: AuthorityApprovalVerificationReason };

type SubscribeAuthorityApprovalSettlementOptions = {
  /** Restricts wake-up hints to the currently visible authority request. */
  expectedRequestId?: string;
  /** Restricts the authoritative request to the currently visible conversation. */
  expectedConversationId?: string | null;
  /** Optional principal binding when the caller already has trusted request context. */
  expectedPrincipalId?: string;
  /** Optional permission binding when the caller already has trusted request context. */
  expectedPermissionId?: string;
  onVerificationStateChange?: (state: AuthorityApprovalVerificationState) => void;
  /** @deprecated Stored settlement replay is removed. This now only cleans legacy state. */
  replayStored?: boolean;
  /** @deprecated Treated as expectedRequestId for source compatibility. */
  replayStoredRequestId?: string;
};

type VerifyAuthorityApprovalHintOptions = {
  expectedRequestId?: string;
  expectedConversationId?: string | null;
  expectedPrincipalId?: string;
  expectedPermissionId?: string;
  now?: number;
  fetchRequest?: (requestId: string) => Promise<AuthorityRequest>;
};

type AuthorityApprovalHintMessage = {
  type: typeof AUTHORITY_APPROVAL_MESSAGE_TYPE;
  hint: AuthorityApprovalHint;
};

function normalizedString(value: unknown, maxLength = 512): string {
  if (typeof value !== "string") return "";
  const normalized = value.trim();
  return normalized.length > maxLength ? "" : normalized;
}

function normalizedConversationId(value: unknown): string | null {
  const normalized = normalizedString(value, 512);
  return normalized || null;
}

function settledStatus(value: unknown): AuthorityApprovalSettlement["status"] | null {
  return value === "approved" || value === "denied" ? value : null;
}

function isHint(value: unknown): value is AuthorityApprovalHint {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return Boolean(normalizedString(record.requestId, 512));
}

function hintFromMessage(value: unknown): AuthorityApprovalHint | null {
  if (isHint(value)) {
    const record = value as Record<string, unknown>;
    return {
      requestId: normalizedString(record.requestId, 512),
      conversationId: normalizedConversationId(record.conversationId),
      issuedAt: Number.isFinite(Number(record.issuedAt ?? record.ts))
        ? Number(record.issuedAt ?? record.ts)
        : undefined,
      nonce: normalizedString(record.nonce, 256) || undefined,
    };
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  if (record.type === AUTHORITY_APPROVAL_MESSAGE_TYPE) {
    return isHint(record.hint) ? hintFromMessage(record.hint) : null;
  }
  if (record.type === LEGACY_AUTHORITY_APPROVAL_MESSAGE_TYPE) {
    return isHint(record.event) ? hintFromMessage(record.event) : null;
  }
  return null;
}

function randomHintNonce(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  }
}

function authorityApprovalHintMessage(event: AuthorityApprovalSettlement): AuthorityApprovalHintMessage {
  return {
    type: AUTHORITY_APPROVAL_MESSAGE_TYPE,
    hint: {
      requestId: normalizedString(event.requestId, 512),
      conversationId: normalizedConversationId(event.conversationId),
      issuedAt: Date.now(),
      nonce: randomHintNonce(),
    },
  };
}

async function fetchAuthorityRequest(requestId: string): Promise<AuthorityRequest> {
  const { api } = await import("./api");
  return api.getAuthorityRequest(requestId);
}

export async function verifyAuthorityApprovalHint(
  rawHint: unknown,
  options: VerifyAuthorityApprovalHintOptions = {},
): Promise<AuthorityApprovalVerificationResult> {
  const hint = hintFromMessage(rawHint);
  if (!hint) return { kind: "ignored", reason: "malformed_hint" };

  const now = options.now ?? Date.now();
  if (hint.issuedAt && Math.abs(now - hint.issuedAt) > AUTHORITY_APPROVAL_HINT_MAX_AGE_MS) {
    return { kind: "ignored", reason: "stale_hint" };
  }

  const expectedRequestId = normalizedString(options.expectedRequestId, 512);
  if (expectedRequestId && hint.requestId !== expectedRequestId) {
    return { kind: "ignored", reason: "unexpected_request" };
  }

  let request: AuthorityRequest;
  try {
    const requestFetcher = options.fetchRequest ?? fetchAuthorityRequest;
    request = await requestFetcher(hint.requestId);
  } catch {
    return { kind: "ignored", reason: "lookup_failed" };
  }

  if (normalizedString(request.request_id, 512) !== hint.requestId) {
    return { kind: "ignored", reason: "request_mismatch" };
  }

  const requestConversationId = normalizedConversationId(request.conversation_id);
  const hintedConversationId = normalizedConversationId(hint.conversationId);
  if (hintedConversationId !== null && requestConversationId !== hintedConversationId) {
    return { kind: "ignored", reason: "conversation_mismatch" };
  }
  if (options.expectedConversationId !== undefined) {
    const expectedConversationId = normalizedConversationId(options.expectedConversationId);
    if (requestConversationId !== expectedConversationId) {
      return { kind: "ignored", reason: "conversation_mismatch" };
    }
  }

  const expectedPrincipalId = normalizedString(options.expectedPrincipalId, 512);
  if (expectedPrincipalId && normalizedString(request.principal_id, 512) !== expectedPrincipalId) {
    return { kind: "ignored", reason: "principal_mismatch" };
  }

  const expectedPermissionId = normalizedString(options.expectedPermissionId, 512);
  if (expectedPermissionId && normalizedString(request.permission_id, 512) !== expectedPermissionId) {
    return { kind: "ignored", reason: "permission_mismatch" };
  }

  const status = settledStatus(request.status);
  if (!status) return { kind: "ignored", reason: "request_not_settled" };

  const settlement: AuthorityApprovalSettlement = {
    requestId: request.request_id,
    status,
    conversationId: requestConversationId,
  };
  return { kind: "verified", settlement, request };
}

export function broadcastAuthorityApprovalSettlement(event: AuthorityApprovalSettlement): void {
  const message = authorityApprovalHintMessage(event);
  if (!message.hint.requestId) return;
  try {
    const channel = new BroadcastChannel(AUTHORITY_APPROVAL_CHANNEL);
    channel.postMessage(message);
    channel.close();
  } catch {
    // BroadcastChannel is optional; the approval decision itself already completed.
  }
  try {
    window.opener?.postMessage(message, window.location.origin);
  } catch {
    // Some dedicated windows do not expose opener.
  }
  // Deliberately do not persist settlement status. Browser channels are wake-up hints only.
}

export function clearStoredAuthorityApprovalSettlement(requestId?: string): void {
  try {
    const stored = window.localStorage.getItem(LEGACY_AUTHORITY_APPROVAL_STORAGE_KEY);
    if (!stored) return;
    if (requestId) {
      const hint = hintFromMessage(JSON.parse(stored));
      if (hint && hint.requestId !== requestId) return;
    }
    window.localStorage.removeItem(LEGACY_AUTHORITY_APPROVAL_STORAGE_KEY);
  } catch {
    // Storage may be unavailable in restricted browser contexts.
  }
}

export function readStoredAuthorityApprovalSettlement(
  options?: { requestId?: string; maxAgeMs?: number },
): AuthorityApprovalSettlement | null {
  // Persisted client state is never settlement evidence. Remove matching legacy state and
  // require the normal authenticated lookup path to determine the current request status.
  clearStoredAuthorityApprovalSettlement(options?.requestId);
  return null;
}

export function subscribeAuthorityApprovalSettlements(
  handler: (event: AuthorityApprovalSettlement) => void,
  options: SubscribeAuthorityApprovalSettlementOptions = {},
): () => void {
  let active = true;
  let channel: BroadcastChannel | null = null;
  let lookupWindowStartedAt = 0;
  let lookupCount = 0;
  const inFlight = new Set<string>();
  const delivered = new Set<string>();
  const expectedRequestId = normalizedString(
    options.expectedRequestId || options.replayStoredRequestId,
    512,
  );

  const lookupAllowed = (requestId: string) => {
    const now = Date.now();
    if (now - lookupWindowStartedAt > AUTHORITY_APPROVAL_LOOKUP_WINDOW_MS) {
      lookupWindowStartedAt = now;
      lookupCount = 0;
    }
    if (lookupCount >= AUTHORITY_APPROVAL_LOOKUP_LIMIT) return false;
    lookupCount += 1;
    return Boolean(requestId);
  };

  const verifyAndDeliver = async (rawHint: unknown) => {
    const hint = hintFromMessage(rawHint);
    if (!hint || !active) return;
    if (expectedRequestId && hint.requestId !== expectedRequestId) return;
    if (inFlight.has(hint.requestId) || !lookupAllowed(hint.requestId)) return;

    inFlight.add(hint.requestId);
    options.onVerificationStateChange?.({ kind: "verifying", requestId: hint.requestId });
    const result = await verifyAuthorityApprovalHint(hint, {
      expectedRequestId: expectedRequestId || undefined,
      expectedConversationId: options.expectedConversationId,
      expectedPrincipalId: options.expectedPrincipalId,
      expectedPermissionId: options.expectedPermissionId,
    });
    inFlight.delete(hint.requestId);
    if (!active) return;
    if (result.kind !== "verified") {
      options.onVerificationStateChange?.({
        kind: "ignored",
        requestId: hint.requestId,
        reason: result.reason,
      });
      return;
    }

    const settlementKey = `${result.settlement.requestId}:${result.settlement.status}:${result.settlement.conversationId ?? ""}`;
    if (delivered.has(settlementKey)) return;
    delivered.add(settlementKey);
    options.onVerificationStateChange?.({ kind: "verified", settlement: result.settlement });
    handler(result.settlement);
  };

  try {
    channel = new BroadcastChannel(AUTHORITY_APPROVAL_CHANNEL);
    channel.onmessage = (event) => {
      void verifyAndDeliver(event.data);
    };
  } catch {
    channel = null;
  }

  const onWindowMessage = (event: MessageEvent) => {
    if (event.origin !== window.location.origin) return;
    void verifyAndDeliver(event.data);
  };
  window.addEventListener("message", onWindowMessage);

  if (options.replayStored) {
    // Clean up versions that persisted a client-declared final state. Do not replay it.
    clearStoredAuthorityApprovalSettlement(expectedRequestId || undefined);
  }

  return () => {
    active = false;
    channel?.close();
    window.removeEventListener("message", onWindowMessage);
  };
}
