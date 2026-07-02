const AUTHORITY_APPROVAL_CHANNEL = "rumi-authority-approval";
const AUTHORITY_APPROVAL_MESSAGE_TYPE = "rumi-authority-approval-settlement";
const AUTHORITY_APPROVAL_STORAGE_KEY = "rumi.authority.approval.settlement";
const AUTHORITY_APPROVAL_STORAGE_MAX_AGE_MS = 5 * 60 * 1000;

export type AuthorityApprovalSettlement = {
  requestId: string;
  status: "approved" | "denied";
  conversationId?: string | null;
};

type SubscribeAuthorityApprovalSettlementOptions = {
  replayStored?: boolean;
  replayStoredRequestId?: string;
};

type StoredAuthorityApprovalSettlement = AuthorityApprovalSettlement & {
  ts: number;
};

function isSettlement(value: unknown): value is AuthorityApprovalSettlement {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return typeof record.requestId === "string"
    && (record.status === "approved" || record.status === "denied");
}

function settlementFromMessage(value: unknown): AuthorityApprovalSettlement | null {
  if (isSettlement(value)) return value;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  if (record.type !== AUTHORITY_APPROVAL_MESSAGE_TYPE) return null;
  return isSettlement(record.event) ? record.event : null;
}

function storedSettlementFromMessage(value: unknown): StoredAuthorityApprovalSettlement | null {
  const settlement = settlementFromMessage(value);
  if (!settlement || !value || typeof value !== "object" || Array.isArray(value)) return null;
  const ts = Number((value as Record<string, unknown>).ts);
  if (!Number.isFinite(ts) || ts <= 0) return null;
  return { ...settlement, ts };
}

export function broadcastAuthorityApprovalSettlement(event: AuthorityApprovalSettlement): void {
  try {
    const channel = new BroadcastChannel(AUTHORITY_APPROVAL_CHANNEL);
    channel.postMessage(event);
    channel.close();
  } catch {
    // BroadcastChannel is optional; the approval decision itself already completed.
  }
  try {
    window.opener?.postMessage({ type: AUTHORITY_APPROVAL_MESSAGE_TYPE, event }, window.location.origin);
  } catch {
    // Some dedicated windows do not expose opener.
  }
  try {
    window.localStorage.setItem(AUTHORITY_APPROVAL_STORAGE_KEY, JSON.stringify({ ...event, ts: Date.now() }));
  } catch {
    // Storage events are only a fallback for browsers without BroadcastChannel.
  }
}

export function clearStoredAuthorityApprovalSettlement(requestId?: string): void {
  try {
    const stored = window.localStorage.getItem(AUTHORITY_APPROVAL_STORAGE_KEY);
    if (!stored) return;
    if (requestId) {
      const settlement = settlementFromMessage(JSON.parse(stored));
      if (settlement && settlement.requestId !== requestId) return;
    }
    window.localStorage.removeItem(AUTHORITY_APPROVAL_STORAGE_KEY);
  } catch {
    // Storage may be unavailable in restricted browser contexts.
  }
}

export function readStoredAuthorityApprovalSettlement(
  options?: { requestId?: string; maxAgeMs?: number },
): AuthorityApprovalSettlement | null {
  try {
    const stored = window.localStorage.getItem(AUTHORITY_APPROVAL_STORAGE_KEY);
    if (!stored) return null;
    const settlement = storedSettlementFromMessage(JSON.parse(stored));
    if (!settlement) {
      window.localStorage.removeItem(AUTHORITY_APPROVAL_STORAGE_KEY);
      return null;
    }
    if (options?.requestId && settlement.requestId !== options.requestId) return null;
    const maxAgeMs = options?.maxAgeMs ?? AUTHORITY_APPROVAL_STORAGE_MAX_AGE_MS;
    if (Date.now() - settlement.ts > maxAgeMs) {
      clearStoredAuthorityApprovalSettlement(settlement.requestId);
      return null;
    }
    return {
      requestId: settlement.requestId,
      status: settlement.status,
      conversationId: settlement.conversationId,
    };
  } catch {
    return null;
  }
}

export function subscribeAuthorityApprovalSettlements(
  handler: (event: AuthorityApprovalSettlement) => void,
  options?: SubscribeAuthorityApprovalSettlementOptions,
): () => void {
  let active = true;
  let channel: BroadcastChannel | null = null;
  try {
    channel = new BroadcastChannel(AUTHORITY_APPROVAL_CHANNEL);
    channel.onmessage = (event) => {
      const settlement = settlementFromMessage(event.data);
      if (settlement) handler(settlement);
    };
  } catch {
    channel = null;
  }
  const onWindowMessage = (event: MessageEvent) => {
    if (event.origin !== window.location.origin) return;
    const settlement = settlementFromMessage(event.data);
    if (settlement) handler(settlement);
  };
  const onStorage = (event: StorageEvent) => {
    if (event.key !== AUTHORITY_APPROVAL_STORAGE_KEY || !event.newValue) return;
    try {
      const settlement = settlementFromMessage(JSON.parse(event.newValue));
      if (settlement) handler(settlement);
    } catch {
      // Ignore malformed fallback messages.
    }
  };
  window.addEventListener("message", onWindowMessage);
  window.addEventListener("storage", onStorage);
  if (options?.replayStored) {
    const replay = () => {
      if (!active) return;
      const settlement = readStoredAuthorityApprovalSettlement({
        requestId: options.replayStoredRequestId,
      });
      if (!settlement) return;
      clearStoredAuthorityApprovalSettlement(settlement.requestId);
      handler(settlement);
    };
    if (typeof window.queueMicrotask === "function") {
      window.queueMicrotask(replay);
    } else {
      window.setTimeout(replay, 0);
    }
  }
  return () => {
    active = false;
    channel?.close();
    window.removeEventListener("message", onWindowMessage);
    window.removeEventListener("storage", onStorage);
  };
}
