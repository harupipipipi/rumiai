import { useEffect, useMemo, useState } from "react";
import { Check, ExternalLink, Loader2, RefreshCw, ShieldAlert, ShieldCheck, ShieldX, X } from "lucide-react";

import { AmbientTriggerPanel } from "../ambient/AmbientTriggerPanel";
import { ambientTriggerClient, type AmbientStatus } from "../ambient/ambientTriggerClient";
import {
  AMBIENT_AUTHORITY_REQUEST_ID,
  AMBIENT_OS_PERMISSIONS,
  AMBIENT_REQUIRED_PERMISSIONS,
  ambientPermissionLabels,
  grantedPermissionCount,
  hasAllRumiPermissions,
} from "../ambient/ambientUiState";
import { authorityApprovalResources, type AuthorityApprovalDecision, type AuthorityRequest } from "../features/chat/resources/authorityApprovalResources";
import {
  authorityApprovalConfig,
  authorityApprovalRuntimeContent,
  authorityApprovalTitle,
  type AuthorityApproval,
  type AuthorityApprovalScope,
} from "../lib/authorityApproval";
import { broadcastAuthorityApprovalSettlement } from "../lib/authorityApprovalEvents";
import { getAuthorityApprovalContext, openAmbientTriggerWindow } from "../lib/desktopApproval";
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
  const isAmbientPackApproval = requestId === AMBIENT_AUTHORITY_REQUEST_ID;
  const [request, setRequest] = useState<AuthorityRequest | null>(null);
  const [pendingRequests, setPendingRequests] = useState<AuthorityRequest[]>([]);
  const [selectedScope, setSelectedScope] = useState<AuthorityApprovalScope>("once");
  const [loading, setLoading] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [action, setAction] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decisionState, setDecisionState] = useState<DecisionState>({ kind: "idle" });
  const [ambientEnabled, setAmbientEnabled] = useState(false);

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
    if (isAmbientPackApproval) return;
    document.title = title;
  }, [isAmbientPackApproval, title]);

  useEffect(() => {
    let cancelled = false;
    const loadAmbient = async () => {
      try {
        const status = await ambientTriggerClient.status();
        if (!cancelled) setAmbientEnabled(Boolean(status.ambient_monitor.enabled));
      } catch {
        if (!cancelled) setAmbientEnabled(false);
      }
    };
    void loadAmbient();
    const timer = window.setInterval(loadAmbient, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!allowedScopes.includes(selectedScope)) {
      setSelectedScope(allowedScopes[0] ?? "once");
    }
  }, [allowedScopes, selectedScope]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (isAmbientPackApproval) {
        setLoading(false);
        setRequest(null);
        setPendingRequests([]);
        return;
      }
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
  }, [isAmbientPackApproval, requestId, refreshNonce]);

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

  if (isAmbientPackApproval) {
    return <AmbientPackAuthorityApprovalWindow />;
  }

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
                  拒否{ambientEnabled ? " (2)" : ""}
                </button>
                <button
                  type="button"
                  onClick={() => void approve()}
                  disabled={controlsDisabled}
                  className="flex h-10 min-w-32 items-center justify-center gap-2 rounded-lg bg-zinc-100 px-4 text-sm font-semibold text-zinc-950 hover:bg-white disabled:opacity-50"
                >
                  {action === "approve" ? <Loader2 className="animate-spin" size={15} /> : <Check size={15} />}
                  承認{ambientEnabled ? " (3)" : ""}
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
      <AmbientTriggerPanel
        approvalTarget={request && request.status === "pending" ? {
          kind: "authority",
          approveLabel: "承認",
          rejectLabel: "拒否",
          canApprove: true,
          canReject: true,
        } : null}
        onApprovalGesture={(decision) => {
          if (controlsDisabled) return;
          if (decision === "approve") void approve();
          else void reject();
        }}
      />
    </main>
  );
}

function AmbientPackAuthorityApprovalWindow() {
  const [status, setStatus] = useState<AmbientStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<"approve" | "open" | "close" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rumiPermissionCount = grantedPermissionCount(status, AMBIENT_REQUIRED_PERMISSIONS, "rumi");
  const osPermissionCount = grantedPermissionCount(status, AMBIENT_OS_PERMISSIONS, "os");
  const rumiReady = hasAllRumiPermissions(status);

  const reloadStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      setStatus(await ambientTriggerClient.status());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "指で録音の状態を取得できませんでした。");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    document.title = "指で録音のRumi許可";
    void reloadStatus();
  }, []);

  const approve = async () => {
    setAction("approve");
    setError(null);
    setMessage(null);
    try {
      let next: AmbientStatus | null = null;
      for (const permissionId of AMBIENT_REQUIRED_PERMISSIONS) {
        next = await ambientTriggerClient.grantPermission(permissionId);
      }
      setStatus(next ?? await ambientTriggerClient.status());
      broadcastAuthorityApprovalSettlement({
        requestId: AMBIENT_AUTHORITY_REQUEST_ID,
        status: "approved",
      });
      setMessage("Rumi側の許可を保存しました。元の画面で端末のマイク・カメラ許可へ進んでください。");
    } catch (approvalError) {
      setError(approvalError instanceof Error ? approvalError.message : "Rumi許可を保存できませんでした。");
    } finally {
      setAction(null);
    }
  };

  const closeWindow = () => {
    setAction("close");
    window.close();
    window.setTimeout(() => setAction(null), 300);
  };

  const openAmbientWindow = async () => {
    setAction("open");
    setError(null);
    try {
      const opened = await openAmbientTriggerWindow();
      if (!opened) {
        window.location.assign("/ambient");
      }
    } catch (openError) {
      console.info("[ambient] ambient trigger window unavailable", openError);
      window.location.assign("/ambient");
    } finally {
      window.setTimeout(() => setAction(null), 300);
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
            <h1 className="mt-2 break-words text-xl font-semibold text-zinc-50">指で録音をRumiで許可</h1>
            <p className="mt-1 text-xs leading-5 text-zinc-500">
              rumi_ambient_trigger_pack が、マイク入力・カメラ検出・AI送信のRumi許可を要求しています。
            </p>
          </div>
          <button
            type="button"
            onClick={() => void reloadStatus()}
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

        {message && (
          <div className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100">
            <div className="flex items-center gap-2 font-medium">
              <ShieldCheck size={16} />
              {message}
            </div>
          </div>
        )}

        <section className="mt-5 grid gap-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
            <div className="flex flex-wrap items-center gap-2">
              {!rumiReady && (
                <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] font-medium text-amber-100">
                  許可が必要
                </span>
              )}
              <span className="rounded border border-zinc-800 px-2 py-1 text-[11px] text-zinc-400">
                Rumi {rumiPermissionCount}/{AMBIENT_REQUIRED_PERMISSIONS.length}
              </span>
              <span className="rounded border border-zinc-800 px-2 py-1 text-[11px] text-zinc-400">
                OS {osPermissionCount}/{AMBIENT_OS_PERMISSIONS.length}
              </span>
            </div>

            {loading ? (
              <div className="mt-5 flex min-h-32 items-center justify-center rounded-lg border border-zinc-800 bg-black/20">
                <Loader2 className="animate-spin text-zinc-500" size={22} />
              </div>
            ) : (
              <div className="mt-5 grid gap-4">
                {rumiReady && (
                  <section className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 p-3 text-xs leading-5 text-emerald-50">
                    <p className="font-medium">Rumiの承認は終わっています</p>
                    <p className="mt-1 text-emerald-50/80">この画面は承認用です。手の認識と録音は、指で録音ウィンドウで開始します。</p>
                  </section>
                )}

                <section className="space-y-2">
                  <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-zinc-600">Rumiで許可すること</p>
                  <div className="grid gap-2">
                    {AMBIENT_REQUIRED_PERMISSIONS.map((permissionId) => (
                      <div key={permissionId} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-black/25 px-3 py-2 text-sm">
                        <span className="text-zinc-200">{ambientPermissionLabels[permissionId] ?? permissionId}</span>
                        <Check size={14} className={rumiReady ? "text-emerald-200" : "text-zinc-600"} />
                      </div>
                    ))}
                  </div>
                </section>

                <section className="rounded-lg border border-zinc-800 bg-black/25 p-3 text-xs leading-5 text-zinc-400">
                  <p className="font-medium text-zinc-200">追加される入口</p>
                  <p className="mt-1">指録音の別ウィンドウ、defaultspack input、LINE / Discord / Web hook の外部入力profileへ接続します。</p>
                </section>

                <section className="rounded-lg border border-zinc-800 bg-black/25 p-3 text-xs leading-5 text-zinc-400">
                  <p className="font-medium text-zinc-200">OS許可とは別管理</p>
                  <p className="mt-1">この画面で保存するのはRumi側の許可です。実際のマイク・カメラ使用は、元の画面でブラウザまたはOSの確認に進みます。</p>
                </section>

                <section className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs leading-5 text-emerald-50">
                  <p className="font-medium">プライバシー</p>
                  <p className="mt-1 text-emerald-50/80">録音データやカメラ映像は残しません。履歴には、指録音を使った時刻と結果だけを残します。</p>
                </section>
              </div>
            )}
          </div>

          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={closeWindow}
              disabled={action !== null}
              className="flex h-10 min-w-28 items-center justify-center gap-2 rounded-lg border border-zinc-800 px-4 text-sm font-semibold text-zinc-300 hover:border-zinc-700 hover:text-zinc-100 disabled:opacity-50"
            >
              {action === "close" ? <Loader2 className="animate-spin" size={15} /> : <X size={15} />}
              {rumiReady ? "閉じる" : "あとで"}
            </button>
            {rumiReady && (
              <button
                type="button"
                onClick={() => void openAmbientWindow()}
                disabled={loading || action !== null}
                className="flex h-10 min-w-40 items-center justify-center gap-2 rounded-lg bg-zinc-100 px-4 text-sm font-semibold text-zinc-950 hover:bg-white disabled:opacity-50"
              >
                {action === "open" ? <Loader2 className="animate-spin" size={15} /> : <ExternalLink size={15} />}
                指で録音を開く
              </button>
            )}
            {!rumiReady && (
              <button
                type="button"
                onClick={() => void approve()}
                disabled={loading || action !== null}
                className="flex h-10 min-w-32 items-center justify-center gap-2 rounded-lg bg-zinc-100 px-4 text-sm font-semibold text-zinc-950 hover:bg-white disabled:opacity-50"
              >
                {action === "approve" ? <Loader2 className="animate-spin" size={15} /> : <Check size={15} />}
                許可する
              </button>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
