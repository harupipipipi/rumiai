import type { ChatUiMessage } from "../renderers/types";

export type AuthorityApproval = {
  requestId: string;
  principalId: string;
  permissionId: string;
  resource: Record<string, unknown>;
  riskLevel?: string;
  summary?: string;
  reason?: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isAuthorityApprovalEvent(event: Record<string, unknown>): boolean {
  return Boolean(
    event.authority
    || event.approval_kind === "authority"
    || event.permission_id === "model.invoke"
    || event.permission_id === "api_key.use",
  );
}

export function pendingAuthorityApproval(messages: ChatUiMessage[]): AuthorityApproval | null {
  for (const message of [...messages].reverse()) {
    if (message.role === "user") return null;
    if (message.role !== "agent") continue;

    for (const event of [...(message.events ?? [])].reverse()) {
      if (event.type !== "approval_requested" && event.phase !== "approval_requested") continue;
      const candidate = event as Record<string, unknown>;
      if (!isAuthorityApprovalEvent(candidate)) continue;
      const requestId = String(candidate.request_id ?? candidate.approval_request_id ?? "").trim();
      if (!requestId) continue;
      const resource = isRecord(candidate.resource) ? candidate.resource : {};
      return {
        requestId,
        principalId: String(candidate.principal_id ?? ""),
        permissionId: String(candidate.permission_id ?? "model.invoke"),
        resource,
        riskLevel: typeof candidate.risk_level === "string" ? candidate.risk_level : undefined,
        summary: typeof candidate.display_summary === "string" ? candidate.display_summary : undefined,
        reason: typeof candidate.reason === "string" ? candidate.reason : undefined,
      };
    }
  }
  return null;
}

export function authorityApprovalRuntimeContent(approval: AuthorityApproval, token?: string): string {
  const payload = {
    request_id: approval.requestId,
    permission_id: approval.permissionId,
    resource: approval.resource,
    ...(token ? { approval_token: token } : {}),
  };
  return [
    "The user approved the pending model/API authority request.",
    "Continue the conversation by retrying the same model/API request once.",
    "Do not ask the user for the same authority approval again unless a new request id is produced.",
    `Authority request id: ${approval.requestId}`,
    `Permission: ${approval.permissionId}`,
    "Authority approval JSON:",
    JSON.stringify(payload, null, 2),
  ].join("\n");
}
