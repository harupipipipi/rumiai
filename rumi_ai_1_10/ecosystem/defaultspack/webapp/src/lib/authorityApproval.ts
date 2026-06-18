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
export type AuthorityApprovalSettledStatus = "approved" | "denied";

type AuthorityApprovalResource = {
  permissionId: string;
  resource: Record<string, unknown>;
};

type AuthorityApprovalRequestLike = {
  request_id?: unknown;
  approval_request_id?: unknown;
  requestId?: unknown;
  principal_id?: unknown;
  principalId?: unknown;
  permission_id?: unknown;
  permissionId?: unknown;
  resource?: unknown;
  risk_level?: unknown;
  riskLevel?: unknown;
  reason?: unknown;
  display_summary?: unknown;
  summary?: unknown;
  display_metadata?: unknown;
};

export const AUTHORITY_WAITING_TEXT = "モデル/API の使用許可が必要です。承認後に続行します。";
export const AUTHORITY_FOLLOWUP_TEXT = "Internal authority resume.";

const AUTHORITY_APPROVAL_BOILERPLATE_PATTERNS = [
  /^\s*The model\/API authority is now approved\.\s*Retrying the request(?: to [^.]{0,360})?\.{1,3}\s*/i,
  /^\s*Thank you for granting the (?:model\/API|model|API) authority request\.\s*I can now use the approved (?:provider|model)[^.]{0,360}\.{1,3}\s*/i,
];

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function stripLeadingMarkdownSeparator(text: string): string {
  return text.replace(/^(?:[ \t]*\r?\n)*[ \t]*-{3,}[ \t]*(?:\r?\n|$)(?:[ \t]*\r?\n)*/, "");
}

export function sanitizeAssistantAuthorityBoilerplate(text: string): string {
  let sanitized = text;
  for (const pattern of AUTHORITY_APPROVAL_BOILERPLATE_PATTERNS) {
    const next = sanitized.replace(pattern, "");
    if (next !== sanitized) {
      return stripLeadingMarkdownSeparator(next).trimStart();
    }
  }
  return sanitized;
}

export function authorityRequestSettledStatus(status: unknown): AuthorityApprovalSettledStatus | null {
  const normalized = String(status ?? "").trim().toLowerCase();
  if (normalized === "approved") return "approved";
  if (normalized === "denied" || normalized === "rejected") return "denied";
  return null;
}

export function authorityApprovalSettledLabel(status: AuthorityApprovalSettledStatus): string {
  return status === "approved" ? "承認済み" : "拒否済み";
}

export function authorityApprovalShouldRetryWithFreshContext(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? "");
  const normalized = message.toLowerCase();
  return [
    "ui_operator expired",
    "ui_operator source is invalid",
    "ui_operator version is invalid",
    "ui_operator timestamps are invalid",
    "ui_operator issued_at is invalid",
    "ui_operator request mismatch",
    "ui_operator signature is invalid",
  ].some((needle) => normalized.includes(needle));
}

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

export function authorityApprovalFromRecord(value: unknown, options?: { assumeAuthority?: boolean }): AuthorityApproval | null {
  if (!isRecord(value)) return null;
  if (!options?.assumeAuthority && !isAuthorityApprovalEvent(value)) return null;
  const requestId = String(value.request_id ?? value.approval_request_id ?? value.requestId ?? "").trim();
  if (!requestId) return null;
  const permissionId = String(value.permission_id ?? value.permissionId ?? "model.invoke").trim() || "model.invoke";
  const resource = isRecord(value.resource) ? value.resource : {};
  return {
    requestId,
    principalId: String(value.principal_id ?? value.principalId ?? ""),
    permissionId,
    resource,
    riskLevel: typeof value.risk_level === "string" ? value.risk_level : typeof value.riskLevel === "string" ? value.riskLevel : undefined,
    summary: typeof value.display_summary === "string" ? value.display_summary : typeof value.summary === "string" ? value.summary : undefined,
    reason: typeof value.reason === "string" ? value.reason : undefined,
  };
}

export function authorityApprovalFromRequest(value: AuthorityApprovalRequestLike | unknown): AuthorityApproval | null {
  if (!isRecord(value)) return null;
  const displayMetadata = isRecord(value.display_metadata) ? value.display_metadata : {};
  const approval = authorityApprovalFromRecord(
    {
      request_id: value.request_id ?? value.approval_request_id ?? value.requestId,
      principal_id: value.principal_id ?? value.principalId,
      permission_id: value.permission_id ?? value.permissionId,
      resource: value.resource,
      risk_level: value.risk_level ?? value.riskLevel ?? displayMetadata.risk_level,
      display_summary: value.display_summary ?? value.summary ?? displayMetadata.summary,
      reason: value.reason,
      authority: true,
    },
    { assumeAuthority: true },
  );
  return approval;
}

export function resolvePendingAuthorityApproval(
  approval: AuthorityApproval | null | undefined,
  pendingRequests: unknown[],
): AuthorityApproval | null {
  if (!approval) return null;
  const pendingApprovals = pendingRequests
    .map((request) => authorityApprovalFromRequest(request))
    .filter((item): item is AuthorityApproval => Boolean(item));
  return (
    pendingApprovals.find((item) => item.requestId === approval.requestId)
    ?? pendingApprovals.find((item) => authorityApprovalGrantMatches(approval, item))
    ?? null
  );
}

function authorityApprovalGrantMatches(left: AuthorityApproval, right: AuthorityApproval): boolean {
  if (left.permissionId !== right.permissionId) return false;
  const keys = [
    "provider_id",
    "api_id",
    "model_id",
    "model_ref",
    "pack_id",
    "domain",
    "endpoint_url",
    "function_id",
    "host_action",
    "operation",
  ];
  let comparableKeys = 0;
  for (const key of keys) {
    const leftValue = stringValue(left.resource?.[key]);
    const rightValue = stringValue(right.resource?.[key]);
    if (!leftValue || !rightValue) continue;
    comparableKeys += 1;
    if (leftValue !== rightValue) return false;
  }
  return comparableKeys > 0;
}

export function pendingAuthorityApproval(messages: ChatUiMessage[]): AuthorityApproval | null {
  for (const message of [...messages].reverse()) {
    if (message.role === "user") return null;
    if (message.role !== "agent") continue;

    const metadata = isRecord(message.metadata) ? message.metadata as Record<string, unknown> : {};
    const metadataApproval = authorityApprovalFromRecord(
      metadata.pendingAuthorityApproval ?? metadata.pending_authority_approval,
      { assumeAuthority: true },
    );
    if (metadataApproval) return metadataApproval;

    for (const event of [...(message.events ?? [])].reverse()) {
      if (event.type !== "approval_requested" && event.phase !== "approval_requested") continue;
      const approval = authorityApprovalFromRecord(event);
      if (approval) return approval;
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

export function authorityRelatedPermissions(approval: AuthorityApprovalResource): string[] {
  const resource = approval.resource ?? {};
  const permissions: string[] = [];
  const providerId = stringValue(resource.provider_id);
  const hasProviderModel = Boolean(providerId && (stringValue(resource.model_id) || stringValue(resource.model_ref)));
  const hasEndpoint = Boolean(stringValue(resource.endpoint_url) || stringValue(resource.domain));
  if (approval.permissionId !== "model.invoke" && hasProviderModel) permissions.push("model.invoke");
  if (approval.permissionId !== "api_key.use" && providerId) permissions.push("api_key.use");
  if (approval.permissionId !== "network.egress" && (hasEndpoint || providerId)) permissions.push("network.egress");
  return permissions;
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
  const isHostApproval = approval.permissionId.startsWith("host.");
  return [
    "Silent internal resume. Continue the interrupted/original user request without any acknowledgment or preface.",
    isHostApproval
      ? "Retry the same host operation once using the supplied resume metadata."
      : "Retry the same model/API operation once using the supplied resume metadata.",
    "In the user-visible answer, never mention approval, authority, API keys, providers, model access, permission, or token details, and do not thank the user for permission.",
    "Do not ask the user for the same permission again unless a new request id is produced.",
    `Request id: ${approval.requestId}`,
    `Permission id: ${approval.permissionId}`,
    "Resume metadata JSON:",
    JSON.stringify(payload, null, 2),
  ].join("\n");
}
