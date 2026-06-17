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

export function authorityApprovalRiskTone(riskLevel?: string): string {
  const normalized = String(riskLevel ?? "").trim().toLowerCase();
  if (normalized === "critical") return "border-red-400/60 bg-red-600/20 text-red-100 ring-1 ring-red-500/25";
  if (normalized === "high") return "border-red-500/35 bg-red-500/10 text-red-200";
  if (normalized === "medium") return "border-amber-500/30 bg-amber-500/10 text-amber-200";
  if (normalized === "low") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
  return "border-sky-500/30 bg-sky-500/10 text-sky-200";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isAuthorityApprovalEvent(event: Record<string, unknown>): boolean {
  const permissionId = typeof event.permission_id === "string" ? event.permission_id : "";
  return Boolean(
    event.authority
    || event.approval_kind === "authority"
    || event.approval_kind === "host_intent"
    || event.approval_kind === "critical_host_function"
    || event.permission_id === "model.invoke"
    || event.permission_id === "api_key.use"
    || event.permission_id === "network.egress"
    || permissionId.startsWith("host.")
    || permissionId.startsWith("authority."),
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
  const operation = typeof resource.operation === "string" ? resource.operation.trim() : "";
  if (providerId) config.provider_ids = [providerId];
  if (apiId) config.api_ids = [apiId];
  if (modelId) config.model_ids = [modelId];
  if (functionId) config.function_ids = [functionId];
  if (packId) config.pack_ids = [packId];
  if (domain) config.domains = [domain];
  const hostActions = Array.from(new Set([hostAction, operation].filter(Boolean)));
  if (hostActions.length) config.host_actions = hostActions;
  if (typeof resource.caller_pack_id === "string" && resource.caller_pack_id.trim()) {
    config.caller_pack_ids = [resource.caller_pack_id.trim()];
  }
  if (typeof resource.caller_function_id === "string" && resource.caller_function_id.trim()) {
    config.caller_function_ids = [resource.caller_function_id.trim()];
  }
  if (resource.port !== undefined && resource.port !== null) config.ports = [resource.port];
  if (resource.stream === true || resource.stream_enabled === true) config.allow_stream = true;
  if (typeof resource.input_tokens === "number" && Number.isFinite(resource.input_tokens)) {
    config.max_input_tokens = resource.input_tokens;
  }
  return config;
}

export function authorityApprovalTitle(approval: AuthorityApprovalResource): string {
  const resource = approval.resource ?? {};
  const app = typeof resource.app_display_name === "string" ? resource.app_display_name : "";
  const providerDisplay = typeof resource.provider_display_name === "string" ? resource.provider_display_name : "";
  const modelDisplay = typeof resource.model_display_name === "string" ? resource.model_display_name : "";
  const endpoint = typeof resource.endpoint_url === "string" ? resource.endpoint_url : "";
  if (app || providerDisplay || modelDisplay || endpoint) {
    const provider = providerDisplay || (typeof resource.provider_id === "string" ? resource.provider_id : "");
    const providerSubject = provider.toLowerCase().endsWith("provider") ? provider : provider && `${provider} provider`;
    const credential = typeof resource.credential_label === "string" && resource.credential_label
      ? resource.credential_label
      : "API key";
    if (endpoint) {
      return `${[app, providerSubject].filter(Boolean).join(" / ")} に ${credential} の使用と ${endpoint} へのアクセスを許可しますか？`;
    }
    return [app, providerSubject].filter(Boolean).join(" / ") || endpoint || approval.permissionId;
  }
  const provider = typeof resource.provider_id === "string" ? resource.provider_id : "";
  const api = typeof resource.api_id === "string" ? resource.api_id : "";
  const model = typeof resource.model_id === "string" ? resource.model_id : "";
  const fn = typeof resource.function_id === "string" ? resource.function_id : "";
  const pack = typeof resource.pack_id === "string" ? resource.pack_id : "";
  const domain = typeof resource.domain === "string" ? resource.domain : "";
  const hostAction = typeof resource.host_action === "string" ? resource.host_action : "";
  const operation = typeof resource.operation === "string" ? resource.operation : "";
  if (approval.permissionId.startsWith("host.") || operation) {
    const callerPack = typeof resource.caller_pack_id === "string" ? resource.caller_pack_id : pack;
    const callerFunction = typeof resource.caller_function_id === "string" ? resource.caller_function_id : fn;
    return [operation || approval.permissionId, callerPack, callerFunction].filter(Boolean).join(" / ") || approval.permissionId;
  }
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
    approval.permissionId.startsWith("host.")
      ? "The user approved the pending host authority request."
      : "The user approved the pending model/API authority request.",
    approval.permissionId.startsWith("host.")
      ? "Continue by retrying the same host intent once with the approved host operation context."
      : "Continue the conversation by retrying the same model/API request once with the approved provider, API key use, and network access context.",
    "Do not ask the user for the same authority approval again unless a new request id is produced.",
    `Authority request id: ${approval.requestId}`,
    `Permission: ${approval.permissionId}`,
    "Authority approval JSON:",
    JSON.stringify(payload, null, 2),
  ].join("\n");
}
