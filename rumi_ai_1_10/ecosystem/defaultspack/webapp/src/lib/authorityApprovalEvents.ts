const AUTHORITY_APPROVAL_CHANNEL = "rumi-authority-approval";
const AUTHORITY_APPROVAL_MESSAGE_TYPE = "rumi-authority-approval-settlement";
const AUTHORITY_APPROVAL_STORAGE_KEY = "rumi.authority.approval.settlement";

export type AuthorityApprovalSettlement = {
  requestId: string;
  status: "approved" | "denied";
  conversationId?: string | null;
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

export function subscribeAuthorityApprovalSettlements(
  handler: (event: AuthorityApprovalSettlement) => void,
): () => void {
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
  return () => {
    channel?.close();
    window.removeEventListener("message", onWindowMessage);
    window.removeEventListener("storage", onStorage);
  };
}
