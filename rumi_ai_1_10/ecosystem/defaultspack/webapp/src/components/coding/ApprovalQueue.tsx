import { Check, RefreshCw, ShieldAlert, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import type { CodingApprovalDecision, CodingApprovalRequest } from "../../lib/api";
import { cn } from "../../lib/cn";
import { codingResources } from "../../features/coding/resources/codingResources";

function formatApprovalTime(value?: number): string {
  if (!value) return "";
  const date = new Date(value > 1_000_000_000_000 ? value : value * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function riskTone(riskLevel?: string): string {
  if (riskLevel === "high" || riskLevel === "blocked") return "text-red-300 border-red-500/30 bg-red-500/10";
  if (riskLevel === "medium") return "text-amber-300 border-amber-500/30 bg-amber-500/10";
  return "text-emerald-300 border-emerald-500/30 bg-emerald-500/10";
}

export function ApprovalQueue({
  initialApprovals,
  limit = 30,
  onApproved,
  refreshSignal = 0,
}: {
  initialApprovals?: CodingApprovalRequest[];
  limit?: number;
  onApproved?: (decision: CodingApprovalDecision, request: CodingApprovalRequest) => void;
  refreshSignal?: number;
}) {
  const [requests, setRequests] = useState<CodingApprovalRequest[]>(initialApprovals ?? []);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (initialApprovals) return;
    setError(null);
    try {
      const result = await codingResources.listCodingApprovals({ limit, include_expired: true });
      setRequests(result.requests);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [initialApprovals, limit]);

  useEffect(() => {
    void load();
  }, [load, refreshSignal]);

  const decide = async (requestId: string, decision: "approve" | "deny") => {
    const request = requests.find((item) => item.request_id === requestId);
    setBusyId(requestId);
    setError(null);
    try {
      if (decision === "approve") {
        const approved = await codingResources.approveCodingApproval(requestId);
        if (request) onApproved?.(approved, request);
      } else {
        await codingResources.denyCodingApproval(requestId, "Denied from coding cockpit");
      }
      await load();
      if (initialApprovals) {
        setRequests((items) => items.map((item) => (
          item.request_id === requestId ? { ...item, status: decision === "approve" ? "approved" : "denied" } : item
        )));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  const pendingCount = requests.filter((request) => request.status === "pending").length;

  return (
    <section className="border-b border-zinc-800/60 p-3" aria-label="Approval queue">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <ShieldAlert size={14} className="text-amber-300" />
          <h2 className="truncate text-xs font-semibold uppercase tracking-wide text-zinc-400">Approvals</h2>
          <span className="rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">{pendingCount}</span>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100"
          title="Refresh approvals"
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {error && <p className="mb-2 rounded border border-red-500/30 bg-red-500/10 px-2 py-1 text-[11px] text-red-200">{error}</p>}

      <div className="space-y-2">
        {requests.slice(0, limit).map((request) => (
          <div key={request.request_id} className="rounded-md border border-zinc-800/80 bg-zinc-950/40 p-2">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-1.5">
                  <span className={cn("rounded border px-1.5 py-0.5 text-[10px]", riskTone(request.risk_level))}>
                    {request.risk_level}
                  </span>
                  <span className="truncate font-mono text-[11px] text-zinc-200">{request.operation}</span>
                </div>
                <p className="mt-1 truncate text-[11px] text-zinc-500">
                  {request.display_summary || request.request_id}
                </p>
              </div>
              <span className="flex-shrink-0 text-[10px] text-zinc-600">{formatApprovalTime(request.created_at)}</span>
            </div>
            {request.status === "pending" ? (
              <div className="mt-2 flex items-center justify-end gap-1">
                <button
                  type="button"
                  disabled={busyId === request.request_id}
                  onClick={() => void decide(request.request_id, "deny")}
                  className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 hover:bg-red-500/10 hover:text-red-200 disabled:opacity-40"
                  title="Deny"
                >
                  <X size={13} />
                </button>
                <button
                  type="button"
                  disabled={busyId === request.request_id}
                  onClick={() => void decide(request.request_id, "approve")}
                  className="flex h-7 w-7 items-center justify-center rounded-md bg-zinc-100 text-zinc-950 hover:bg-white disabled:opacity-40"
                  title="Approve"
                >
                  <Check size={13} />
                </button>
              </div>
            ) : (
              <p className="mt-2 text-right text-[10px] uppercase tracking-wide text-zinc-600">{request.status}</p>
            )}
          </div>
        ))}
        {requests.length === 0 && <p className="py-3 text-center text-[11px] text-zinc-600">No approvals</p>}
      </div>
    </section>
  );
}
