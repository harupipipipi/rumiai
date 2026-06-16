import { useEffect, useMemo, useState } from "react";
import { Check, Loader2, RefreshCw, ShieldAlert, ShieldCheck, ShieldX, X } from "lucide-react";

import { authorityApprovalResources, type AuthorityApprovalDecision, type AuthorityRequest } from "../features/chat/resources/authorityApprovalResources";
import {
  authorityApprovalConfig,
  authorityApprovalRuntimeContent,
  authorityApprovalTitle,
  type AuthorityApproval,
  type AuthorityApprovalScope,
} from "../lib/authorityApproval";
import { broadcastAuthorityApprovalSettlement } from "../lib/authorityApprovalEvents";
import { getAuthorityApprovalContext } from "../lib/desktopApproval";
import { cn } from "../lib/cn";

type DecisionState =
  | { kind: "idle" }
  | { kind: "approved"; decision: AuthorityApprovalDecision; resumed: boolean }
  | { kind: "rejected" };

const SCOPE_LABELS: Record<AuthorityApprovalScope, string> = {
  once: "今回のみ",
  conversation: "会話",
  profile: "Profile",
  node: "Node",
};

function requestIdFromLocation(): string {
  try {
    return new URLSearchParams(window.location.search).get("request_id")?.trim() ?? "";
  } catch {
    return "";
  }
}

function requestToApproval(request: AuthorityRequest): AuthorityApproval {
  return {
    requestId: request.request_id,
    principalId: request.principal_id,
    permissionId: request.permission_id,
    resource: request.resource ?? {},
    riskLevel: request.risk_level || request.display_metadata?.risk_level,
    summary: request.display_metadata?.summary || request.reason,
    reason: request.reason,
  };
}

function stableJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formattedDate(value: string | null | undefined): string {
  if (!value) return "なし";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function relatedPermissionsForApproval(approval: AuthorityApproval): string[] {
  const resource = approval.resource ?? {};
  const permissions: string[] = [];
  const hasProviderModel = Boolean(stringValue(resource.provider_id) && (stringValue(resource.model_id) || stringValue(resource.model_ref)));
  const hasEndpoint = Boolean(stringValue(resource.endpoint_url) || stringValue(resource.domain));
  if (approval.permissionId !== "model.invoke" && hasProviderModel) permissions.push("model.invoke");
  if (approval.permissionId !== "api_key.use" && stringValue(resource.provider_id)) permissions.push("api_key.use");
  if (approval.permissionId !== "network.egress" && hasEndpoint) permissions.push("network.egress");
  return permissions;
}

function windowTitle(request: AuthorityRequest | null): string {
  if (!request) return "Authority approval";
  return request.display_metadata?.title || authorityApprovalTitle(requestToApproval(request));
}

export function AuthorityApprovalWindow() {
  const [requestId, setRequestId] = useState(requestIdFromLocation());
  const [request, setRequest] = useState<AuthorityRequest | null>(null);
  const [pendingRequests, setPendingRequests] = useState<AuthorityRequest[]>([]);
  const [selectedScope, setSelectedScope] = useState<AuthorityApprovalScope>("once");
  const [loading, setLoading] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [action, setAction] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decisionState, setDecisionState] = useState<DecisionState>({ kind: "idle" });

  const approval = useMemo(() => request ? requestToApproval(request) : null, [request]);
  const title = request ? windowTitle(request) : "Authority approval";
  const detailRows = useMemo(() => {
    if (!request) return [];
    const resource = request.resource ?? {};
    const metadata = request.display_metadata ?? {};
    return [
      { label: "app", value: metadata.app_display_name || metadata.pack_id || stringValue(resource.app_display_name) || stringValue(resource.pack_id) },
      { label: "provider", value: metadata.provider_display_name || metadata.provider_id || stringValue(resource.provider_display_name) || stringValue(resource.provider_id) },
      { label: "model", value: metadata.model_display_name || metadata.model_id || stringValue(resource.model_display_name) || stringValue(resource.model_id) },
      { label: "API key", value: metadata.credential_label || stringValue(resource.credential_label) || "secret value is never shown" },
      { label: "endpoint", value: metadata.endpoint_url || stringValue(resource.endpoint_url) || metadata.endpoint_host || stringValue(resource.domain) },
      { label: "expires", value: formattedDate(request.expires_at) },
    ].filter((row) => row.value);
  }, [request]);
  const allowedScopes = useMemo<AuthorityApprovalScope[]>(() => {
    const scopes = request?.allowed_scopes?.filter((scope): scope is AuthorityApprovalScope => (
      scope === "once" || scope === "conversation" || scope === "profile" || scope === "node"
    )) ?? [];
    return scopes.length ? scopes : ["once"];
  }, [request?.allowed_scopes]);
  const controlsDisabled = !request || request.status !== "pending" || action !== null || decisionState.kind !== "idle";

  useEffect(() => {
    document.title = title;
  }, [title]);

  useEffect(() => {
    if (!allowedScopes.includes(selectedScope)) {
      setSelectedScope(allowedScopes[0] ?? "once");
    }
  }, [allowedScopes, selectedScope]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      setDecisionState({ kind: "idle" });
      try {
        const [single, list] = await Promise.all([
          requestId ? authorityApprovalResources.getAuthorityRequest(requestId) : Promise.resolve(null),
          authorityApprovalResources.listAuthorityRequests({ status: "pending" }),
        ]);
        if (cancelled) return;
        setRequest(single);
        setPendingRequests(list.pending ?? []);
      } catch (loadError) {
        if (cancelled) return;
        setRequest(null);
        setError(loadError instanceof Error ? loadError.message : "承認リクエストを取得できませんでした。");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [requestId, refreshNonce]);

  const selectRequest = (nextRequestId: string) => {
    if (!nextRequestId || nextRequestId === requestId) return;
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set("request_id", nextRequestId);
    window.history.replaceState(null, "", nextUrl.toString());
    setRequestId(nextRequestId);
  };

  const refresh = async () => {
    setRefreshNonce((value) => value + 1);
  };

  const approve = async () => {
    if (!request || !approval) return;
    setAction("approve");
    setError(null);
    try {
      const context = await getAuthorityApprovalContext(request.request_id);
      const decision = await authorityApprovalResources.approveAuthorityApproval(request.request_id, {
        scope: selectedScope,
        config: authorityApprovalConfig(approval),
        related_permissions: relatedPermissionsForApproval(approval),
        ui_operator: context.ui_operator,
      });
      if (!decision.approved) throw new Error("authority approval failed");

      let resumed = false;
      if (request.conversation_id) {
        const approvalFollowups = [
          ...(decision.token ? [{
            approval_token: decision.token,
            request_id: request.request_id,
            permission_id: request.permission_id,
          }] : []),
          ...((decision.related_approvals ?? [])
            .filter((item) => item.token && item.request_id && item.permission_id)
            .map((item) => ({
              approval_token: item.token,
              request_id: item.request_id,
              permission_id: item.permission_id,
            }))),
        ];
        await authorityApprovalResources.sendAuthorityResume(
          request.conversation_id,
          "ユーザーがモデル/API の使用を許可しました。承認済みのリクエストとして続行してください。",
          {
            authority_followup: {
              ...(decision.token ? { approval_token: decision.token } : {}),
              request_id: request.request_id,
              permission_id: request.permission_id,
              approvals: approvalFollowups,
              hidden: true,
            },
            chat_display: {
              hidden: true,
              reason: "authority_followup",
            },
            runtime_content: authorityApprovalRuntimeContent(approval, decision.token),
          },
        );
        resumed = true;
      }
      setDecisionState({ kind: "approved", decision, resumed });
      setRequest({ ...request, status: "approved" });
      setPendingRequests((current) => current.filter((item) => item.request_id !== request.request_id));
      broadcastAuthorityApprovalSettlement({
        requestId: request.request_id,
        status: "approved",
        conversationId: request.conversation_id,
      });
    } catch (approvalError) {
      setError(approvalError instanceof Error ? approvalError.message : "authority 承認に失敗しました。");
    } finally {
      setAction(null);
    }
  };

  const reject = async () => {
    if (!request) return;
    setAction("reject");
    setError(null);
    try {
      const context = await getAuthorityApprovalContext(request.request_id);
      await authorityApprovalResources.denyAuthorityApproval(request.request_id, {
        reason: "Denied from dedicated authority approval window",
        persist: false,
        ui_operator: context.ui_operator,
      });
      setDecisionState({ kind: "rejected" });
      setRequest({ ...request, status: "denied" });
      setPendingRequests((current) => current.filter((item) => item.request_id !== request.request_id));
      broadcastAuthorityApprovalSettlement({
        requestId: request.request_id,
        status: "denied",
        conversationId: request.conversation_id,
      });
    } catch (rejectionError) {
      setError(rejectionError instanceof Error ? rejectionError.message : "authority 承認の拒否に失敗しました。");
    } finally {
      setAction(null);
    }
  };

  return (
    <main className="min-h-screen bg-[#09090b] text-zinc-100">
      <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col px-5 py-5">
        <header className="flex items-start justify-between gap-4 border-b border-zinc-800 pb-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-zinc-500">
              <ShieldAlert size={14} />
              Authority
            </div>
            <h1 className="mt-2 break-words text-xl font-semibold text-zinc-50">{title}</h1>
            <p className="mt-1 text-xs leading-5 text-zinc-500">{request?.display_metadata?.summary || request?.reason || "pending request"}</p>
          </div>
          <button
            type="button"
            onClick={() => void refresh()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100"
            title="再読み込み"
          >
            <RefreshCw size={15} />
          </button>
        </header>

        {error && (
          <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-100">
            {error}
          </div>
        )}

        {decisionState.kind !== "idle" && (
          <div className={cn(
            "mt-4 rounded-lg border px-3 py-3 text-sm",
            decisionState.kind === "approved"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-100"
              : "border-zinc-700 bg-zinc-900 text-zinc-200",
          )}>
            <div className="flex items-center gap-2 font-medium">
              {decisionState.kind === "approved" ? <ShieldCheck size={16} /> : <ShieldX size={16} />}
              {decisionState.kind === "approved" ? "承認しました" : "拒否しました"}
            </div>
            {decisionState.kind === "approved" && (
              <p className="mt-1 text-xs text-emerald-200/80">
                scope: {decisionState.decision.scope}{decisionState.resumed ? " / assistant resume sent" : ""}
              </p>
            )}
          </div>
        )}

        <section className="mt-5 grid gap-4">
          {loading ? (
            <div className="flex min-h-56 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-950">
              <Loader2 className="animate-spin text-zinc-500" size={22} />
            </div>
          ) : request && approval ? (
            <>
              <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn(
                    "rounded border px-2 py-1 text-[11px] font-medium",
                    request.risk_level === "high"
                      ? "border-red-500/30 bg-red-500/10 text-red-200"
                      : "border-sky-500/30 bg-sky-500/10 text-sky-200",
                  )}>
                    {request.risk_level || "authority"}
                  </span>
                  <span className="rounded border border-zinc-800 px-2 py-1 text-[11px] text-zinc-400">
                    {request.permission_id}
                  </span>
                  <span className="rounded border border-zinc-800 px-2 py-1 text-[11px] text-zinc-400">
                    {request.status}
                  </span>
                </div>

                <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2">
                  {detailRows.map((row) => (
                    <div key={row.label} className={row.label === "endpoint" ? "sm:col-span-2" : undefined}>
                      <dt className="text-zinc-600">{row.label}</dt>
                      <dd className="mt-1 break-words text-zinc-200">{row.value}</dd>
                    </div>
                  ))}
                </dl>

                <div className="mt-4 rounded-lg border border-zinc-800 bg-black/30 p-3">
                  <p className="text-[11px] font-medium text-zinc-400">scope</p>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    {allowedScopes.map((scope) => (
                      <button
                        key={scope}
                        type="button"
                        disabled={controlsDisabled}
                        onClick={() => setSelectedScope(scope)}
                        className={cn(
                          "flex h-9 items-center justify-center rounded-lg border text-xs font-medium transition-colors disabled:opacity-50",
                          selectedScope === scope
                            ? "border-zinc-100 bg-zinc-100 text-zinc-950"
                            : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100",
                        )}
                      >
                        {SCOPE_LABELS[scope]}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="mt-4 rounded-lg border border-zinc-800 bg-black/30 p-3">
                  <p className="text-[11px] font-medium text-zinc-400">audit</p>
                  <p className="mt-1 text-xs leading-5 text-zinc-500">
                    {request.display_metadata?.audit_text || "Approving records a signed local UI-operator action."}
                  </p>
                </div>

                <details className="mt-4 text-xs text-zinc-500">
                  <summary className="cursor-pointer select-none hover:text-zinc-300">resource</summary>
                  <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-zinc-800 bg-black/40 p-3 font-mono text-[11px]">
                    {stableJson(request.resource)}
                  </pre>
                </details>
              </div>

              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => void reject()}
                  disabled={controlsDisabled}
                  className="flex h-10 min-w-28 items-center justify-center gap-2 rounded-lg border border-zinc-800 px-4 text-sm font-semibold text-zinc-300 hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-100 disabled:opacity-50"
                >
                  {action === "reject" ? <Loader2 className="animate-spin" size={15} /> : <X size={15} />}
                  拒否
                </button>
                <button
                  type="button"
                  onClick={() => void approve()}
                  disabled={controlsDisabled}
                  className="flex h-10 min-w-32 items-center justify-center gap-2 rounded-lg bg-zinc-100 px-4 text-sm font-semibold text-zinc-950 hover:bg-white disabled:opacity-50"
                >
                  {action === "approve" ? <Loader2 className="animate-spin" size={15} /> : <Check size={15} />}
                  承認
                </button>
              </div>
            </>
          ) : (
            <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4 text-sm text-zinc-400">
              request_id が見つかりません。
            </div>
          )}
        </section>

        {pendingRequests.length > 1 && (
          <section className="mt-5 border-t border-zinc-800 pt-4">
            <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-zinc-600">Pending</p>
            <div className="mt-2 grid gap-2">
              {pendingRequests.map((item) => (
                <button
                  key={item.request_id}
                  type="button"
                  onClick={() => selectRequest(item.request_id)}
                  className={cn(
                    "flex min-w-0 items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left text-xs",
                    item.request_id === requestId
                      ? "border-sky-500/40 bg-sky-500/10 text-sky-100"
                      : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100",
                  )}
                >
                  <span className="min-w-0 truncate">{windowTitle(item)}</span>
                  <span className="shrink-0 text-[10px] text-zinc-600">{item.risk_level}</span>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
