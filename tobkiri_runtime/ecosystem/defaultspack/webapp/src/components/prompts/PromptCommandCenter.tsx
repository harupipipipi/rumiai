import { FileText, RefreshCw, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { PromptUsageSegment, PromptUsageSummary } from "../../lib/api";
import { PromptUsageSegmentCard } from "./PromptUsageSegmentCard";
import { allPromptUsageSegments, orderPromptCommandSegments, tokenText } from "./promptSegmentView";

type PromptCommandCenterProps = {
  profileId?: string;
  conversationId?: string | null;
  loadPromptActive: (params: { profile_id?: string; conversation_id?: string; include_text?: boolean }) => Promise<PromptUsageSummary>;
  togglePromptEdge: (payload: { profile_id?: string; conversation_id?: string; edge_id: string; enabled: boolean }) => Promise<PromptUsageSummary>;
  onOpenStudio?: (promptId?: string) => void;
};

export function PromptCommandCenter({ profileId, conversationId, loadPromptActive, togglePromptEdge, onOpenStudio }: PromptCommandCenterProps) {
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState<PromptUsageSummary | null>(null);
  const [busyEdge, setBusyEdge] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const segments = useMemo(() => orderPromptCommandSegments(allPromptUsageSegments(summary)), [summary]);
  const activeCount = segments.filter((segment) => segment.status === "active").length;
  const inactiveCount = segments.filter((segment) => segment.status !== "active").length;
  const gatedCount = segments.filter((segment) => segment.status === "gated").length;
  const totalTokens = Number(summary?.token_estimate?.total ?? segments.reduce((sum, segment) => sum + Number(segment.tokens ?? 0), 0));

  const load = () => {
    void loadPromptActive({ profile_id: profileId, conversation_id: conversationId ?? undefined })
      .then((result) => {
        setSummary(result);
        setError(null);
      })
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Prompt summary could not be loaded."));
  };

  useEffect(load, [profileId, conversationId]);

  const toggleSegment = (segment: PromptUsageSegment) => {
    const edgeId = String(segment.edge_id ?? "").trim();
    if (!edgeId || segment.allow_disable === false) return;
    setBusyEdge(edgeId);
    void togglePromptEdge({
      profile_id: profileId,
      conversation_id: conversationId ?? undefined,
      edge_id: edgeId,
      enabled: segment.status !== "active",
    })
      .then((result) => {
        setSummary(result);
        setError(null);
      })
      .catch((toggleError) => setError(toggleError instanceof Error ? toggleError.message : "Prompt toggle failed."))
      .finally(() => setBusyEdge(null));
  };

  return (
    <div className="pointer-events-auto mx-auto mb-2 w-full max-w-5xl px-4">
      <div className="flex items-center justify-between gap-2 rounded-xl border border-zinc-800 bg-zinc-950/80 px-3 py-2 shadow-[0_18px_50px_rgba(0,0,0,0.28)] backdrop-blur">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex min-w-0 items-center gap-2 text-left"
          aria-label="Open Prompt Command Center"
        >
          <FileText size={15} className="shrink-0 text-cyan-300" />
          <span className="truncate text-xs font-semibold text-zinc-100">Prompts</span>
          <span className="shrink-0 rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400">
            {activeCount} active
          </span>
          {gatedCount > 0 && <span className="shrink-0 font-mono text-[10px] text-sky-300">{gatedCount} gated</span>}
          {inactiveCount > 0 && <span className="shrink-0 font-mono text-[10px] text-amber-300">{inactiveCount} off</span>}
          <span className="hidden shrink-0 font-mono text-[10px] text-zinc-500 sm:inline">{tokenText(totalTokens)}</span>
        </button>
        <div className="flex shrink-0 items-center gap-1">
          <button type="button" onClick={load} className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200" aria-label="Refresh prompts">
            <RefreshCw size={13} />
          </button>
          <button type="button" onClick={() => onOpenStudio?.()} className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-900 hover:text-cyan-200" aria-label="Open Prompt Studio">
            <SlidersHorizontal size={13} />
          </button>
        </div>
      </div>
      {error && <div className="mt-1 rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-100">{error}</div>}

      {open && (
        <div className="fixed inset-0 rumi-layer-modal flex justify-end bg-black/45" role="dialog" aria-modal="true" aria-label="Prompt Command Center">
          <div className="flex h-full w-[min(560px,100vw)] flex-col border-l border-zinc-800 bg-zinc-950 text-zinc-200 shadow-2xl">
            <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-zinc-100">Prompt Command Center</div>
                <div className="mt-0.5 truncate text-[11px] text-zinc-500">{activeCount} active · {inactiveCount} inactive · {tokenText(totalTokens)}</div>
              </div>
              <button type="button" onClick={() => setOpen(false)} className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200" aria-label="Close Prompt Command Center">
                <X size={16} />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
              <div className="grid gap-2">
                {segments.map((segment) => (
                  <PromptUsageSegmentCard
                    key={`${segment.id}-${segment.status}`}
                    segment={segment}
                    variant="command"
                    busy={busyEdge === String(segment.edge_id ?? "").trim()}
                    onToggle={toggleSegment}
                    onInspect={onOpenStudio}
                  />
                ))}
                {!segments.length && (
                  <div className="rounded-xl border border-dashed border-zinc-800 px-4 py-8 text-center text-sm text-zinc-500">
                    Prompt graph summary is empty for this profile.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
