const AUTHORITY_APPROVAL_CHANNEL = "rumi-authority-approval";

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

export function broadcastAuthorityApprovalSettlement(event: AuthorityApprovalSettlement): void {
  try {
    const channel = new BroadcastChannel(AUTHORITY_APPROVAL_CHANNEL);
    channel.postMessage(event);
    channel.close();
  } catch {
    // BroadcastChannel is optional; the approval decision itself already completed.
  }
}

export function subscribeAuthorityApprovalSettlements(
  handler: (event: AuthorityApprovalSettlement) => void,
): () => void {
  try {
    const channel = new BroadcastChannel(AUTHORITY_APPROVAL_CHANNEL);
    channel.onmessage = (event) => {
      if (isSettlement(event.data)) handler(event.data);
    };
    return () => channel.close();
  } catch {
    return () => {};
  }
}
