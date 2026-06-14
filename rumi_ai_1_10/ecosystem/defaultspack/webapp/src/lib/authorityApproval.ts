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

export type AuthorityApprovalScope = "once" | "conversation" | "profile" | "node";

type AuthorityApprovalResource = {
  permissionId: string;
  resource: Record<string, unknown>;
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

export function authorityApprovalConfig(approval: AuthorityApprovalResource): Record<string, unknown> {
  const resource = approval.resource ?? {};
  const config: Record<string, unknown> = {};
  const providerId = typeof resource.provider_id === "string" ? resource.provider_id.trim() : "";
  const apiId = typeof resource.api_id === "string" ? resource.api_id.trim() : "";
  const modelId = typeof resource.model_id === "string" ? resource.model_id.trim() : "";
  const functionId = typeof resource.function_id === "string" ? resource.function_id.trim() : "";
  const packId = typeof resource.pack_id === "string" ? resource.pack_id.trim() : "";
  const domain = typeof resource.domain === "string" ? resource.domain.trim() : "";
  const hostAction = typeof resource.host_action === "string" ? resource.host_action.trim() : "";
  if (providerId) config.provider_ids = [providerId];
  if (apiId) config.api_ids = [apiId];
  if (modelId) config.model_ids = [modelId];
  if (functionId) config.function_ids = [functionId];
  if (packId) config.pack_ids = [packId];
  if (domain) config.domains = [domain];
  if (hostAction) config.host_actions = [hostAction];
  if (resource.port !== undefined && resource.port !== null) config.ports = [resource.port];
  if (resource.stream === true) config.allow_stream = true;
  if (typeof resource.input_tokens === "number" && Number.isFinite(resource.input_tokens)) {
    config.max_input_tokens = resource.input_tokens;
  }
  return config;
}

export function authorityApprovalTitle(approval: AuthorityApprovalResource): string {
  const resource = approval.resource ?? {};
  const provider = typeof resource.provider_id === "string" ? resource.provider_id : "";
  const api = typeof resource.api_id === "string" ? resource.api_id : "";
  const model = typeof resource.model_id === "string" ? resource.model_id : "";
  const fn = typeof resource.function_id === "string" ? resource.function_id : "";
  const pack = typeof resource.pack_id === "string" ? resource.pack_id : "";
  const domain = typeof resource.domain === "string" ? resource.domain : "";
  const hostAction = typeof resource.host_action === "string" ? resource.host_action : "";
  return [provider, api, model, fn, pack, domain, hostAction].filter(Boolean).join(" / ") || approval.permissionId;
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
