import { useMemo, useState } from "react";
import { AlertTriangle, Check, Clock3, Eye, RefreshCw, ShieldAlert, UserRound, Wrench, X } from "lucide-react";

import { api, type ApprovalRequest } from "../lib/api";
import { cn } from "../lib/cn";

export function approvalRiskRank(risk?: string): number {
  const normalized = String(risk ?? "low").toLowerCase();
  if (normalized === "critical") return 4;
  if (normalized === "high") return 3;
  if (normalized === "medium") return 2;
  if (normalized === "low") return 1;
  return 0;
}

export function sortApprovals(approvals: ApprovalRequest[]): ApprovalRequest[] {
  return [...approvals].sort((a, b) => {
    const statusDelta = Number(a.status !== "pending") - Number(b.status !== "pending");
    const riskDelta = approvalRiskRank(b.risk_level) - approvalRiskRank(a.risk_level);
    const aTime = a.created_at ? Date.parse(String(a.created_at)) : 0;
    const bTime = b.created_at ? Date.parse(String(b.created_at)) : 0;
    return statusDelta || riskDelta || bTime - aTime || a.id.localeCompare(b.id);
  });
}

export function riskTone(risk?: string): string {
  const rank = approvalRiskRank(risk);
  if (rank >= 4) return "border-red-500/40 bg-red-500/10 text-red-200";
  if (rank === 3) return "border-orange-500/35 bg-orange-500/10 text-orange-200";
  if (rank === 2) return "border-amber-500/30 bg-amber-500/10 text-amber-200";
  return "border-emerald-500/25 bg-emerald-500/10 text-emerald-300";
}

function compactJson(value: unknown): string {
  if (!value) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return text.length > 700 ? `${text.slice(0, 700)}...` : text;
}

function formatTime(value?: number | string | null): string {
  if (!value) return "";
  const time = typeof value === "number" ? value : Date.parse(String(value));
  if (!Number.isFinite(time)) return String(value);
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(time);
}

export function ApprovalCenter({
  approvals,
  loading = false,
  selectedId,
  onRefresh,
  onSelect,
  onApprove,
  onReject,
}: {
  approvals: ApprovalRequest[];
  loading?: boolean;
  selectedId?: string | null;
  onRefresh?: () => void;
  onSelect?: (approval: ApprovalRequest) => void;
  onApprove?: (approval: ApprovalRequest, reason?: string) => Promise<void> | void;
  onReject?: (approval: ApprovalRequest, reason?: string) => Promise<void> | void;
}) {
  const [statusFilter, setStatusFilter] = useState("pending");
  const [riskFilter, setRiskFilter] = useState("all");
  const [reason, setReason] = useState("");
  const [busyId, setBusyId] = useState("");
  const [message, setMessage] = useState("");
  const sorted = useMemo(() => sortApprovals(approvals), [approvals]);
  const filtered = useMemo(() => sorted.filter((approval) => {
    const statusOk = statusFilter === "all" || approval.status === statusFilter;
    const riskOk = riskFilter === "all" || approval.risk_level === riskFilter;
    return statusOk && riskOk;
  }), [riskFilter, sorted, statusFilter]);
  const risks = useMemo(() => ["all", ...Array.from(new Set(approvals.map((approval) => approval.risk_level || "low")))], [approvals]);
  const pendingCount = approvals.filter((approval) => approval.status === "pending").length;

  const decide = async (approval: ApprovalRequest, decision: "approve" | "reject") => {
    setBusyId(approval.id);
    setMessage("");
    try {
      if (decision === "approve") {
        if (onApprove) await onApprove(approval, reason.trim() || undefined);
        else await api.approveApproval(approval.id, reason.trim() || undefined);
      } else if (onReject) {
        await onReject(approval, reason.trim() || undefined);
      } else {
        await api.rejectApproval(approval.id, reason.trim() || undefined);
      }
      setReason("");
      setMessage(decision === "approve" ? "Approved" : "Rejected");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Decision failed");
    } finally {
      setBusyId("");
    }
  };

  return (
    <section className="flex h-full min-h-0 flex-col bg-[#09090b] text-zinc-100">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">Approval Center</h2>
          <p className="mt-0.5 truncate text-[11px] text-zinc-500">{pendingCount} pending · {approvals.length} total</p>
        </div>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
            title="Refresh approvals"
          >
            <RefreshCw size={14} /> Refresh
          </button>
        )}
      </header>

      <div className="flex flex-wrap gap-2 border-b border-zinc-800 px-4 py-3">
        {["pending", "all", "approved", "rejected"].map((status) => (
          <button
            key={status}
            type="button"
            onClick={() => setStatusFilter(status)}
            className={cn(
              "h-8 rounded-md border px-2.5 text-xs font-medium transition-colors",
              statusFilter === status ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200" : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:bg-zinc-800",
            )}
          >
            {status}
          </button>
        ))}
        <select
          value={riskFilter}
          onChange={(event) => setRiskFilter(event.target.value)}
          className="h-8 rounded-lg border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-100 outline-none focus:border-zinc-600"
        >
          {risks.map((risk) => (
            <option key={risk} value={risk}>
              {risk}
            </option>
          ))}
        </select>
        <input
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Decision note"
          className="h-8 min-w-[180px] flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-100 outline-none focus:border-zinc-600"
        />
      </div>

      {message && <div className="border-b border-zinc-800 px-4 py-2 text-xs text-zinc-400">{message}</div>}

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="grid gap-3 xl:grid-cols-2">
          {filtered.map((approval) => {
            const busy = busyId === approval.id;
            return (
              <article
                key={approval.id}
                className={cn(
                  "overflow-hidden rounded-lg border bg-zinc-950/60",
                  selectedId === approval.id ? "border-emerald-500/40" : "border-zinc-800",
                )}
              >
                <button
                  type="button"
                  onClick={() => onSelect?.(approval)}
                  className="flex w-full items-start gap-3 px-3 py-3 text-left hover:bg-zinc-900/70"
                >
                  <span className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-400">
                    <ShieldAlert size={16} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-medium", riskTone(approval.risk_level))}>
                        {approval.risk_level || "low"}
                      </span>
                      <span className="rounded-full border border-zinc-800 bg-zinc-900 px-2 py-0.5 text-[10px] text-zinc-400">
                        {approval.status}
                      </span>
                    </span>
                    <span className="mt-1 block truncate text-sm font-medium text-zinc-100">
                      {approval.action || approval.tool_name || approval.id}
                    </span>
                    <span className="mt-1 block truncate text-[11px] text-zinc-500">{approval.reason || "approval requested"}</span>
                  </span>
                </button>

                <div className="grid gap-px border-t border-zinc-800 bg-zinc-800 text-[11px] text-zinc-500 md:grid-cols-3">
                  <div className="flex min-w-0 items-center gap-1.5 bg-zinc-950 px-3 py-2">
                    <UserRound size={13} /> <span className="truncate">{approval.agent_name || approval.agent_id || "agent"}</span>
                  </div>
                  <div className="flex min-w-0 items-center gap-1.5 bg-zinc-950 px-3 py-2">
                    <Wrench size={13} /> <span className="truncate">{approval.tool_name || "tool"}</span>
                  </div>
                  <div className="flex min-w-0 items-center gap-1.5 bg-zinc-950 px-3 py-2">
                    <Clock3 size={13} /> <span className="truncate">{formatTime(approval.created_at)}</span>
                  </div>
                </div>

                {(approval.screenshot_url || approval.snapshot_ref) && (
                  <div className="grid gap-3 border-t border-zinc-800 p-3 md:grid-cols-[140px_1fr]">
                    {approval.screenshot_url ? (
                      <img src={approval.screenshot_url} alt="Approval screenshot" className="h-24 w-full rounded-lg border border-zinc-800 object-cover" />
                    ) : (
                      <div className="flex h-24 items-center justify-center rounded-lg border border-zinc-800 text-zinc-600">
                        <Eye size={16} />
                      </div>
                    )}
                    <pre className="max-h-24 overflow-auto whitespace-pre-wrap rounded-lg border border-zinc-800 bg-zinc-950 p-2 text-[10px] text-zinc-500">
                      {approval.snapshot_ref || compactJson(approval.payload)}
                    </pre>
                  </div>
                )}

                {!approval.screenshot_url && !approval.snapshot_ref && approval.payload && (
                  <pre className="max-h-28 overflow-auto whitespace-pre-wrap border-t border-zinc-800 p-3 text-[10px] text-zinc-500">
                    {compactJson(approval.payload)}
                  </pre>
                )}

                <footer className="flex flex-wrap justify-end gap-2 border-t border-zinc-800 px-3 py-2">
                  <button
                    type="button"
                    onClick={() => decide(approval, "reject")}
                    disabled={busy || approval.status !== "pending"}
                    className="flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                    title="Reject approval"
                  >
                    <X size={13} /> Reject
                  </button>
                  <button
                    type="button"
                    onClick={() => decide(approval, "approve")}
                    disabled={busy || approval.status !== "pending"}
                    className="flex h-7 items-center gap-1 rounded-md bg-zinc-100 px-2 text-[11px] font-semibold text-zinc-950 hover:bg-white disabled:opacity-50"
                    title="Approve action"
                  >
                    <Check size={13} /> Approve
                  </button>
                </footer>
              </article>
            );
          })}
          {filtered.length === 0 && (
            <div className="flex min-h-[180px] items-center justify-center rounded-lg border border-dashed border-zinc-800 text-sm text-zinc-500 xl:col-span-2">
              {loading ? "Loading approvals..." : "No approvals match the current filter."}
            </div>
          )}
        </div>
      </div>

      {pendingCount > 0 && (
        <footer className="flex items-center gap-2 border-t border-zinc-800 px-4 py-2 text-[11px] text-amber-200">
          <AlertTriangle size={13} /> {pendingCount} pending
        </footer>
      )}
    </section>
  );
}
