import { AlertTriangle, CheckCircle2, FileSearch, RefreshCw, RotateCw, SplitSquareHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { CodingDiffResponse, CodingGitStatus } from "../../lib/api";
import type { ChangeRequestRecord } from "../../lib/changeRequests";
import { createChangeRequest, listChangeRequests, refreshChangeRequest } from "../../lib/changeRequests";
import { codingResources } from "../../features/coding/resources/codingResources";
import { FilesChangedPane, filesFromStatusAndDiff } from "./FilesChangedPane";

type DetailTab = "summary" | "files" | "checks" | "review" | "seal";
type ReviewFilter = "open" | "closed";

function statusSignature(status: CodingGitStatus | null): string {
  if (!status) return "";
  return JSON.stringify({
    staged: [...(status.staged ?? [])].sort(),
    modified: [...(status.modified ?? [])].sort(),
    untracked: [...(status.untracked ?? [])].sort(),
    porcelain: status.porcelain ?? "",
  });
}

function checkLabel(review: ChangeRequestRecord): string {
  const checks = review.check_summary;
  if (!checks) return "checks pending";
  if (checks.label) return checks.label;
  if (checks.failed) return `${checks.failed} failing`;
  if (checks.pending) return `${checks.pending} pending`;
  if (checks.passed || checks.total) return `${checks.passed ?? checks.total} passing`;
  return "checks pending";
}

function compactDate(value?: string): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function ReviewListItem({
  review,
  selected,
  onSelect,
}: {
  review: ChangeRequestRecord;
  selected: boolean;
  onSelect: (review: ChangeRequestRecord) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(review)}
      className={`w-full rounded-md border px-2 py-1.5 text-left ${
        selected ? "border-sky-500/40 bg-sky-500/10" : "border-zinc-800 bg-zinc-950/40 hover:bg-zinc-900/70"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate font-mono text-[11px] text-zinc-200">{review.id}</span>
        <span className="flex-shrink-0 rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">{review.status}</span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-zinc-600">
        <span className="truncate">{review.title || review.summary || "Working tree review"}</span>
        <span className="flex-shrink-0">{checkLabel(review)}</span>
      </div>
    </button>
  );
}

function Placeholder({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-black/20 p-3">
      <p className="text-xs font-semibold text-zinc-300">{title}</p>
      <p className="mt-1 text-[11px] leading-relaxed text-zinc-600">{text}</p>
    </div>
  );
}

export function ChangeReviewPanel({ workspaceId }: { workspaceId?: string | null }) {
  const [status, setStatus] = useState<CodingGitStatus | null>(null);
  const [diff, setDiff] = useState<CodingDiffResponse | null>(null);
  const [reviews, setReviews] = useState<ChangeRequestRecord[]>([]);
  const [selectedReviewId, setSelectedReviewId] = useState<string>("working-tree");
  const [filter, setFilter] = useState<ReviewFilter>("open");
  const [detailTab, setDetailTab] = useState<DetailTab>("summary");
  const [apiAvailable, setApiAvailable] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const changedFiles = useMemo(() => filesFromStatusAndDiff(status, diff), [status, diff]);
  const workingTreeSignature = useMemo(() => statusSignature(status), [status]);
  const selectedReview = reviews.find((review) => review.id === selectedReviewId) ?? null;
  const displayFiles = selectedReview?.files?.length ? selectedReview.files : changedFiles;
  const displayDiff = selectedReview?.snapshot?.diff ?? diff?.diff ?? "";
  const dirty = !status?.clean && changedFiles.length > 0;
  const untrackedCount = changedFiles.filter((file) => file.untracked).length;
  const highRiskCount = changedFiles.filter((file) => file.highRisk).length;
  const stale = Boolean(selectedReview?.snapshot?.signature && workingTreeSignature && selectedReview.snapshot.signature !== workingTreeSignature);
  const visibleReviews = reviews.filter((review) => {
    const closed = String(review.status).toLowerCase().includes("closed");
    return filter === "closed" ? closed : !closed;
  });

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [nextStatus, nextDiff, nextReviews] = await Promise.all([
        codingResources.getGitStatus({ workspace_id: workspaceId }),
        codingResources.getGitDiff({ workspace_id: workspaceId }),
        listChangeRequests({ workspace_id: workspaceId }),
      ]);
      setStatus(nextStatus);
      setDiff(nextDiff);
      setReviews(nextReviews.reviews);
      setApiAvailable(nextReviews.apiAvailable);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreateReview = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await createChangeRequest({ workspace_id: workspaceId });
      if (created) {
        setReviews((items) => [created, ...items.filter((item) => item.id !== created.id)]);
        setSelectedReviewId(created.id);
      } else {
        setApiAvailable(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRefreshReview = async () => {
    if (!selectedReview) return;
    setBusy(true);
    setError(null);
    try {
      const refreshed = await refreshChangeRequest(selectedReview.id, { workspace_id: workspaceId });
      if (refreshed) {
        setReviews((items) => items.map((item) => item.id === refreshed.id ? refreshed : item));
      } else {
        setApiAvailable(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="border-b border-zinc-800/60 p-3" aria-label="Rumi Review">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <FileSearch size={14} className="text-teal-300" />
          <h2 className="truncate text-xs font-semibold uppercase tracking-wide text-zinc-400">Rumi Review</h2>
          <span className="truncate font-mono text-[10px] text-zinc-600">{status?.branch ?? "working tree"}</span>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void load()}
          className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40"
          title="Refresh review desk"
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {error && <p className="mb-2 rounded border border-red-500/30 bg-red-500/10 px-2 py-1 text-[11px] text-red-200">{error}</p>}
      {!apiAvailable && (
        <p className="mb-2 rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-100">
          Change request API is not enabled yet; working tree review remains local.
        </p>
      )}

      <div className="rounded-md border border-zinc-800 bg-zinc-950/40 p-2">
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={() => {
              setSelectedReviewId("working-tree");
              setDetailTab("summary");
            }}
            className="min-w-0 text-left"
          >
            <p className="truncate text-xs font-semibold text-zinc-200">Working Tree</p>
            <p className="mt-0.5 text-[10px] text-zinc-600">{dirty ? "dirty" : "clean"} candidate</p>
          </button>
          <button
            type="button"
            onClick={() => void handleCreateReview()}
            disabled={busy || !dirty}
            className="h-7 flex-shrink-0 rounded-md bg-zinc-100 px-2 text-[11px] font-semibold text-zinc-950 hover:bg-white disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-600"
          >
            Create Review
          </button>
        </div>
        <div className="mt-2 grid grid-cols-4 gap-1.5">
          <div className="rounded border border-zinc-800 bg-black/20 px-2 py-1">
            <p className="text-[10px] text-zinc-600">Files</p>
            <p className="font-mono text-xs text-zinc-200">{changedFiles.length}</p>
          </div>
          <div className="rounded border border-zinc-800 bg-black/20 px-2 py-1">
            <p className="text-[10px] text-zinc-600">Untracked</p>
            <p className="font-mono text-xs text-amber-200">{untrackedCount}</p>
          </div>
          <div className="rounded border border-zinc-800 bg-black/20 px-2 py-1">
            <p className="text-[10px] text-zinc-600">Dirty</p>
            <p className="font-mono text-xs text-zinc-200">{dirty ? "yes" : "no"}</p>
          </div>
          <div className="rounded border border-zinc-800 bg-black/20 px-2 py-1">
            <p className="text-[10px] text-zinc-600">Risk</p>
            <p className="font-mono text-xs text-red-200">{highRiskCount}</p>
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-2 min-[1440px]:grid-cols-[150px_minmax(0,1fr)]">
        <div className="space-y-2">
          <div className="flex rounded-md border border-zinc-800 bg-black/20 p-0.5">
            {(["open", "closed"] as const).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setFilter(item)}
                className={`h-6 flex-1 rounded px-2 text-[10px] capitalize ${
                  filter === item ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {item}
              </button>
            ))}
          </div>
          <div className="space-y-1.5">
            {visibleReviews.map((review) => (
              <ReviewListItem
                key={review.id}
                review={review}
                selected={selectedReviewId === review.id}
                onSelect={(nextReview) => {
                  setSelectedReviewId(nextReview.id);
                  setDetailTab("summary");
                }}
              />
            ))}
            {visibleReviews.length === 0 && <p className="rounded-md border border-zinc-800 bg-black/20 px-2 py-4 text-center text-[11px] text-zinc-600">No {filter} reviews</p>}
          </div>
        </div>

        <div className="min-w-0 space-y-2">
          {stale && (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2">
              <div className="flex items-center gap-2">
                <AlertTriangle size={13} className="text-amber-200" />
                <p className="text-xs font-semibold text-amber-100">Review is stale</p>
              </div>
              <p className="mt-1 text-[11px] text-amber-100/80">working tree changed after this review was created</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <button type="button" onClick={() => setDetailTab("files")} className="h-7 rounded-md border border-amber-500/30 px-2 text-[11px] text-amber-100 hover:bg-amber-500/10">
                  View original snapshot
                </button>
                <button type="button" onClick={() => void handleRefreshReview()} disabled={busy} className="flex h-7 items-center gap-1 rounded-md border border-amber-500/30 px-2 text-[11px] text-amber-100 hover:bg-amber-500/10 disabled:opacity-50">
                  <RotateCw size={12} /> Refresh review
                </button>
                <button type="button" onClick={() => setSelectedReviewId("working-tree")} className="flex h-7 items-center gap-1 rounded-md border border-amber-500/30 px-2 text-[11px] text-amber-100 hover:bg-amber-500/10">
                  <SplitSquareHorizontal size={12} /> Compare drift
                </button>
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-1">
            {(["summary", "files", "checks", "review", "seal"] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setDetailTab(tab)}
                className={`h-7 rounded-md px-2 text-[11px] capitalize ${
                  detailTab === tab ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-300"
                }`}
              >
                {tab === "files" ? "Files changed" : tab}
              </button>
            ))}
          </div>

          {detailTab === "summary" && (
            <div className="rounded-md border border-zinc-800 bg-black/20 p-3">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={14} className="text-teal-300" />
                <p className="text-xs font-semibold text-zinc-200">{selectedReview?.title ?? "Working tree candidate"}</p>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
                {selectedReview?.summary ?? "Local snapshot candidate for AI review. Phase 1 shows files, risk tags, and API-backed review records when available."}
              </p>
              <div className="mt-2 flex flex-wrap gap-1">
                {selectedReview?.created_at && <span className="rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">created {compactDate(selectedReview.created_at)}</span>}
                <span className="rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">{checkLabel(selectedReview ?? { id: "working-tree", status: "open" })}</span>
              </div>
            </div>
          )}
          {detailTab === "files" && <FilesChangedPane files={displayFiles} diff={displayDiff} />}
          {detailTab === "checks" && <Placeholder title="Checks not enabled" text="Check execution will attach to change_request records in a later phase. This view is read-only for now." />}
          {detailTab === "review" && <Placeholder title="AI review not enabled" text="Reviewer findings and threaded notes are not active yet. No remote review or external service is called from this panel." />}
          {detailTab === "seal" && <Placeholder title="Seal actions not enabled" text="This phase intentionally does not commit, push, or publish changes." />}
        </div>
      </div>
    </section>
  );
}
