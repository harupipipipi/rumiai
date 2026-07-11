import { RotateCcw, Save, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { CodingCheckpoint, CodingDiffResponse } from "../../lib/api";
import { codingResources } from "../../features/coding/resources/codingResources";
import { codingActionRequiresApproval } from "./approvalQueueSync";

function checkpointLabel(checkpoint: CodingCheckpoint): string {
  return String(checkpoint.snapshot_id || checkpoint.path || "checkpoint");
}

export type ApprovedCheckpointDecision = {
  request_id: string;
  approved?: boolean;
  token?: string;
  nonce: number;
};

export function codingApprovalRequestId(result: unknown): string {
  if (!result || typeof result !== "object" || Array.isArray(result)) return "";
  const record = result as Record<string, unknown>;
  const approvalRequest = record.approval_request;
  const nested = approvalRequest && typeof approvalRequest === "object" && !Array.isArray(approvalRequest)
    ? approvalRequest as Record<string, unknown>
    : null;
  return String(record.approval_request_id ?? nested?.request_id ?? "").trim();
}

export function CheckpointPanel({
  workspaceId,
  initialCheckpoints,
  initialDiff,
  onActionResult,
  approvedDecision,
}: {
  workspaceId?: string | null;
  initialCheckpoints?: CodingCheckpoint[];
  initialDiff?: CodingDiffResponse;
  onActionResult?: (result: unknown) => void;
  approvedDecision?: ApprovedCheckpointDecision | null;
}) {
  const [checkpoints, setCheckpoints] = useState<CodingCheckpoint[]>(initialCheckpoints ?? []);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>("");
  const [diff, setDiff] = useState<CodingDiffResponse | null>(initialDiff ?? null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingRestore, setPendingRestore] = useState<{
    requestId: string;
    snapshotId: string;
    workspaceId: string | null;
  } | null>(null);
  const handledApprovalKeys = useRef<Set<string>>(new Set());

  const load = useCallback(async () => {
    if (initialCheckpoints) return;
    setError(null);
    try {
      const result = await codingResources.listCodingCheckpoints({ workspace_id: workspaceId, limit: 20 });
      setCheckpoints(result.checkpoints);
      setSelectedSnapshotId((current) => current || result.checkpoints[0]?.snapshot_id || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [initialCheckpoints, workspaceId]);

  const loadDiff = useCallback(async () => {
    if (initialDiff) return;
    try {
      const result = await codingResources.getGitDiff({ workspace_id: workspaceId });
      setDiff(result);
    } catch {
      setDiff(null);
    }
  }, [initialDiff, workspaceId]);

  useEffect(() => {
    void load();
    void loadDiff();
  }, [load, loadDiff]);

  const createCheckpoint = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await codingResources.createCodingCheckpoint({
        workspace_id: workspaceId,
        paths: ["."],
        operation: "cockpit",
      });
      const createdSnapshotId = checkpointLabel(result.checkpoint);
      setCheckpoints((items) => [
        result.checkpoint,
        ...items.filter((item) => checkpointLabel(item) !== createdSnapshotId),
      ]);
      setSelectedSnapshotId(createdSnapshotId);
      setMessage(`Created ${createdSnapshotId}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const restoreCheckpoint = async () => {
    if (!selectedSnapshotId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await codingResources.restoreCodingSnapshot(selectedSnapshotId, { workspace_id: workspaceId });
      onActionResult?.(result);
      const approvalRequired = codingActionRequiresApproval(result);
      const requestId = codingApprovalRequestId(result);
      setPendingRestore(
        approvalRequired && requestId
          ? {
              requestId,
              snapshotId: selectedSnapshotId,
              workspaceId: workspaceId ?? null,
            }
          : null,
      );
      setMessage(approvalRequired ? "Approval required" : `Restored ${selectedSnapshotId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!approvedDecision?.approved || !approvedDecision.token || !pendingRestore) return;
    if (approvedDecision.request_id !== pendingRestore.requestId) return;
    const key = `${approvedDecision.nonce}:${approvedDecision.request_id}`;
    if (handledApprovalKeys.current.has(key)) return;
    handledApprovalKeys.current.add(key);

    const retryRestore = async () => {
      setBusy(true);
      setError(null);
      setMessage(`Restoring ${pendingRestore.snapshotId}`);
      try {
        const result = await codingResources.restoreCodingSnapshot(
          pendingRestore.snapshotId,
          {
            workspace_id: pendingRestore.workspaceId,
            approval_token: approvedDecision.token,
          },
        );
        onActionResult?.(result);
        if (codingActionRequiresApproval(result)) {
          const requestId = codingApprovalRequestId(result);
          setPendingRestore(
            requestId
              ? {
                  requestId,
                  snapshotId: pendingRestore.snapshotId,
                  workspaceId: pendingRestore.workspaceId,
                }
              : null,
          );
          setMessage("Approval required");
          return;
        }
        setPendingRestore(null);
        setMessage(`Restored ${pendingRestore.snapshotId}`);
        await loadDiff();
      } catch (err) {
        setMessage(null);
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    };

    void retryRestore();
  }, [approvedDecision, loadDiff, onActionResult, pendingRestore, workspaceId]);

  return (
    <section className="border-b border-zinc-800/60 p-3" aria-label="Checkpoints">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="truncate text-xs font-semibold uppercase tracking-wide text-zinc-400">Checkpoints</h2>
        <button
          type="button"
          disabled={busy}
          onClick={() => void createCheckpoint()}
          className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40"
          title="Create checkpoint"
        >
          <Save size={13} />
        </button>
      </div>

      {error && <p className="mb-2 rounded border border-red-500/30 bg-red-500/10 px-2 py-1 text-[11px] text-red-200">{error}</p>}
      {message && <p className="mb-2 rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-300">{message}</p>}

      <div className="flex items-center gap-1.5">
        <select
          value={selectedSnapshotId}
          onChange={(event) => setSelectedSnapshotId(event.target.value)}
          className="h-8 min-w-0 flex-1 rounded-md border border-zinc-800 bg-zinc-950/40 px-2 font-mono text-[11px] text-zinc-300 outline-none"
        >
          {checkpoints.map((checkpoint) => (
            <option key={checkpointLabel(checkpoint)} value={checkpoint.snapshot_id} className="bg-zinc-900 text-zinc-100">
              {checkpointLabel(checkpoint)}
            </option>
          ))}
          {checkpoints.length === 0 && <option value="">no checkpoints</option>}
        </select>
        <button
          type="button"
          disabled={busy || !selectedSnapshotId}
          onClick={() => void restoreCheckpoint()}
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md text-amber-300 hover:bg-amber-500/10 disabled:opacity-40"
          title="Restore checkpoint"
        >
          <RotateCcw size={13} />
        </button>
      </div>

      <div className="mt-2 rounded-md border border-zinc-800 bg-black/30 p-2">
        <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-zinc-600">
          <ShieldAlert size={11} />
          Restore diff
        </div>
        <pre className="max-h-28 overflow-auto whitespace-pre-wrap font-mono text-[10px] leading-relaxed text-zinc-500">
          {diff?.diff || "No diff"}
        </pre>
      </div>
    </section>
  );
}
