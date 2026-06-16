import { Eye, FileText, Lock, RefreshCw, ShieldCheck, SlidersHorizontal, Sparkles, ToggleLeft, ToggleRight, Wrench, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { PromptUsageSegment, PromptUsageSummary } from "../../lib/api";
import { cn } from "../../lib/cn";

type PromptCommandCenterProps = {
  profileId?: string;
  conversationId?: string | null;
  loadPromptActive: (params: { profile_id?: string; conversation_id?: string; include_text?: boolean }) => Promise<PromptUsageSummary>;
  togglePromptEdge: (payload: { profile_id?: string; conversation_id?: string; edge_id: string; enabled: boolean }) => Promise<PromptUsageSummary>;
  onOpenStudio?: (promptId?: string) => void;
};

function allSegments(summary?: PromptUsageSummary | null): PromptUsageSegment[] {
  if (!summary) return [];
  return summary.segments ?? [...(summary.active_segments ?? []), ...(summary.disabled_segments ?? [])];
}

function segmentRank(segment: PromptUsageSegment): number {
  if (segment.status === "disabled") return 0;
  if (segment.status === "gated") return 1;
  if (segment.status === "budget-dropped") return 2;
  if (segment.status === "active") return 4;
  return 3;
}

function orderPromptCommandSegments(segments: PromptUsageSegment[]): PromptUsageSegment[] {
  return [...segments].sort((a, b) => segmentRank(a) - segmentRank(b));
}

function tokenText(value: unknown): string {
  const n = Number(value ?? 0);
  return Number.isFinite(n) && n > 0 ? `${n.toLocaleString()} tokens` : "0 tokens";
}

function statusTone(status: string | undefined): string {
  if (status === "active") return "text-emerald-300";
  if (status === "disabled" || status === "budget-dropped") return "text-amber-300";
  if (status === "gated") return "text-sky-300";
  return "text-zinc-400";
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  if (typeof value === "string") return value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
  return [];
}

function compactText(value: unknown, fallback = ""): string {
  const text = String(value ?? fallback).trim();
  return text.length > 180 ? `${text.slice(0, 177)}...` : text;
}

function safetySummary(segment: PromptUsageSegment): string {
  const safety = recordFromUnknown(segment.safety_boundary);
  return compactText(safety.summary, "Passive text only: cannot grant permissions, call tools, or mutate chat state.");
}

function activationLine(segment: PromptUsageSegment): string {
  const detail = recordFromUnknown(segment.activation_detail);
  return compactText(detail.effect || segment.input_role || "model input segment");
}

function sourceLine(segment: PromptUsageSegment): string {
  const detail = recordFromUnknown(segment.activation_detail);
  return compactText(detail.trigger || segment.source_priority || segment.source || segment.source_type || "profile selection");
}

function signalLine(segment: PromptUsageSegment): { icon: typeof Wrench; label: string; text: string } | null {
  const tool = recordFromUnknown(segment.tool_signal);
  if (Object.keys(tool).length > 0) {
    const skills = stringList(tool.skills);
    const skillSuffix = skills.length ? ` Skill hints: ${skills.slice(0, 3).join(", ")}.` : "";
    return {
      icon: Wrench,
      label: "Tool signal",
      text: compactText(`${tool.display_name || tool.tool_name || tool.tool_id || "Tool"} is visible as schema metadata only.${skillSuffix}`),
    };
  }
  const skill = recordFromUnknown(segment.skill_signal);
  if (Object.keys(skill).length > 0) {
    return {
      icon: Sparkles,
      label: "Skill trigger",
      text: compactText(skill.triggered_by || "Runtime skill matched this turn."),
    };
  }
  return null;
}

export function PromptCommandCenter({ profileId, conversationId, loadPromptActive, togglePromptEdge, onOpenStudio }: PromptCommandCenterProps) {
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState<PromptUsageSummary | null>(null);
  const [busyEdge, setBusyEdge] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const segments = useMemo(() => orderPromptCommandSegments(allSegments(summary)), [summary]);
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
                {segments.map((segment) => {
                  const edgeId = String(segment.edge_id ?? "").trim();
                  const canToggle = Boolean(edgeId) && segment.allow_disable !== false;
                  const isActive = segment.status === "active";
                  const signal = signalLine(segment);
                  const SignalIcon = signal?.icon;
                  return (
                    <div key={`${segment.id}-${segment.status}`} className="rounded-xl border border-zinc-800 bg-zinc-900/35 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <span className={cn("text-[11px] font-semibold", statusTone(segment.status))}>{segment.status ?? "available"}</span>
                            <span className="min-w-0 truncate text-sm font-semibold text-zinc-100">{segment.label || segment.prompt_id || segment.id}</span>
                          </div>
                          <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-zinc-500">
                            <span>{segment.kind || segment.source_type || "prompt"}</span>
                            <span>{tokenText(segment.tokens)}</span>
                            <span className="max-w-full truncate font-mono">{segment.source || segment.source_type}</span>
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          <button
                            type="button"
                            disabled={!canToggle || busyEdge === edgeId}
                            onClick={() => toggleSegment(segment)}
                            className={cn(
                              "rounded-md p-1.5",
                              canToggle ? "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100" : "cursor-not-allowed text-zinc-700",
                            )}
                            title={canToggle ? (isActive ? "Disable prompt segment" : "Enable prompt segment") : "This segment cannot be disabled"}
                            aria-label={canToggle ? (isActive ? "Disable prompt segment" : "Enable prompt segment") : "Prompt segment cannot be disabled"}
                          >
                            {canToggle ? (isActive ? <ToggleRight size={17} /> : <ToggleLeft size={17} />) : <Lock size={15} />}
                          </button>
                          <button
                            type="button"
                            onClick={() => onOpenStudio?.(segment.prompt_id || segment.id)}
                            className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-cyan-200"
                            aria-label="Inspect prompt in Prompt Studio"
                          >
                            <Eye size={15} />
                          </button>
                        </div>
                      </div>
                      <div className="mt-2 rounded-lg border border-zinc-800/80 bg-black/20 px-2.5 py-2 text-[11px] leading-relaxed text-zinc-300">
                        {segment.explanation || segment.reason || "Included by the prompt graph."}
                      </div>
                      <div className="mt-2 grid gap-1.5 text-[11px] text-zinc-500">
                        <div className="flex min-w-0 items-center gap-2">
                          <SlidersHorizontal size={12} className="shrink-0 text-cyan-300/80" />
                          <span className="min-w-0 truncate">{activationLine(segment)}</span>
                        </div>
                        <div className="flex min-w-0 items-center gap-2">
                          <FileText size={12} className="shrink-0 text-zinc-500" />
                          <span className="min-w-0 truncate">{sourceLine(segment)}</span>
                        </div>
                        <div className="flex min-w-0 items-center gap-2">
                          <ShieldCheck size={12} className="shrink-0 text-emerald-300/80" />
                          <span className="min-w-0 truncate">{safetySummary(segment)}</span>
                        </div>
                        {signal && SignalIcon && (
                          <div className="flex min-w-0 items-center gap-2">
                            <SignalIcon size={12} className="shrink-0 text-violet-300/80" />
                            <span className="min-w-0 truncate">{signal.label}: {signal.text}</span>
                          </div>
                        )}
                      </div>
                      {(segment.text || segment.preview) && (
                        <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap rounded-lg border border-zinc-800 bg-black/25 p-2 font-mono text-[11px] leading-relaxed text-zinc-300">
                          {segment.text || segment.preview}
                        </pre>
                      )}
                    </div>
                  );
                })}
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
