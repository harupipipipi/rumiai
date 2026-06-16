import { ChevronDown, FileText, Lock, ShieldCheck, SlidersHorizontal, Sparkles, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { PromptUsageSegment, PromptUsageSummary } from "../../lib/api";
import { cn } from "../../lib/cn";

type PromptUsageDisclosureProps = {
  usage?: PromptUsageSummary | null;
  loadPromptTrace?: (traceId: string, profileId?: string) => Promise<PromptUsageSummary>;
};

function segmentStatusClass(status: string | undefined): string {
  if (status === "active") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-200";
  if (status === "budget-dropped") return "border-amber-500/25 bg-amber-500/10 text-amber-200";
  if (status === "gated") return "border-sky-500/25 bg-sky-500/10 text-sky-200";
  return "border-zinc-700 bg-zinc-900/60 text-zinc-300";
}

function segmentKindLabel(segment: PromptUsageSegment): string {
  return String(segment.kind || segment.source_type || "prompt").replace(/_/g, " ");
}

function tokenLabel(value: unknown): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n) || n <= 0) return "0 tokens";
  return `${n.toLocaleString()} tokens`;
}

function usageSegments(usage?: PromptUsageSummary | null): PromptUsageSegment[] {
  if (!usage) return [];
  return usage.segments ?? [
    ...(usage.active_segments ?? []),
    ...(usage.disabled_segments ?? []),
  ];
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function compactText(value: unknown, fallback = ""): string {
  const text = String(value ?? fallback).trim();
  return text.length > 170 ? `${text.slice(0, 167)}...` : text;
}

function detailLine(segment: PromptUsageSegment): string {
  const detail = recordFromUnknown(segment.activation_detail);
  return compactText(detail.effect || segment.input_role || detail.trigger || segment.source_priority || "model input segment");
}

function safetyLine(segment: PromptUsageSegment): string {
  const safety = recordFromUnknown(segment.safety_boundary);
  return compactText(safety.summary, "Passive text only: cannot grant permissions, call tools, or mutate chat state.");
}

function signalLine(segment: PromptUsageSegment): { kind: "tool" | "skill"; text: string } | null {
  const tool = recordFromUnknown(segment.tool_signal);
  if (Object.keys(tool).length > 0) {
    return { kind: "tool", text: compactText(`${tool.display_name || tool.tool_name || tool.tool_id || "Tool"} is visible as schema metadata; prompt text cannot execute it.`) };
  }
  const skill = recordFromUnknown(segment.skill_signal);
  if (Object.keys(skill).length > 0) return { kind: "skill", text: compactText(skill.triggered_by || "Runtime skill matched this turn.") };
  return null;
}

export function PromptUsageDisclosure({ usage, loadPromptTrace }: PromptUsageDisclosureProps) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<PromptUsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const traceId = String(usage?.trace_id ?? "").trim();
  const profileId = String(usage?.profile_id ?? "").trim();
  const segments = useMemo(() => usageSegments(detail ?? usage), [detail, usage]);
  const activeCount = Number((detail ?? usage)?.active_count ?? segments.filter((segment) => segment.status === "active").length);
  const disabledCount = Number((detail ?? usage)?.disabled_count ?? segments.filter((segment) => segment.status !== "active").length);
  const totalTokens = Number((detail ?? usage)?.token_estimate?.total ?? 0);

  useEffect(() => {
    if (!open || !traceId || detail || segments.some((segment) => segment.text) || !loadPromptTrace) return;
    let cancelled = false;
    void loadPromptTrace(traceId, profileId || undefined)
      .then((result) => {
        if (!cancelled) {
          setDetail(result);
          setError(null);
        }
      })
      .catch((fetchError) => {
        if (!cancelled) setError(fetchError instanceof Error ? fetchError.message : "Prompt trace could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [detail, loadPromptTrace, open, profileId, segments, traceId]);

  if (!usage || (!traceId && segments.length === 0)) return null;

  return (
    <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-950/55 text-zinc-300">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex min-h-10 w-full items-center justify-between gap-3 px-3 py-2 text-left"
        aria-expanded={open}
      >
        <span className="flex min-w-0 items-center gap-2">
          <FileText size={14} className="shrink-0 text-cyan-300" />
          <span className="truncate text-xs font-semibold text-zinc-100">Prompt used</span>
          <span className="shrink-0 rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400">
            {activeCount} segments
          </span>
          {disabledCount > 0 && (
            <span className="shrink-0 rounded border border-amber-500/20 bg-amber-500/10 px-1.5 py-0.5 font-mono text-[10px] text-amber-200">
              {disabledCount} not active
            </span>
          )}
          <span className="shrink-0 font-mono text-[10px] text-zinc-500">{tokenLabel(totalTokens)}</span>
        </span>
        <ChevronDown size={14} className={cn("shrink-0 text-zinc-500 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="border-t border-zinc-800 px-3 py-3">
          {error && <div className="mb-3 rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-100">{error}</div>}
          <div className="grid gap-2">
            {segments.map((segment) => (
              <div key={`${segment.id}-${segment.status}`} className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-2">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className={cn("rounded border px-1.5 py-0.5 text-[10px] font-medium", segmentStatusClass(segment.status))}>{segment.status ?? "available"}</span>
                  <span className="min-w-0 truncate text-xs font-semibold text-zinc-100">{segment.label || segment.prompt_id || segment.id}</span>
                  <span className="rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">{segmentKindLabel(segment)}</span>
                  <span className="font-mono text-[10px] text-zinc-500">{tokenLabel(segment.tokens)}</span>
                  {segment.allow_disable === false && <Lock size={11} className="text-zinc-500" />}
                  {segment.editable && <SlidersHorizontal size={11} className="text-cyan-300" />}
                </div>
                <div className="mt-1 rounded-md border border-zinc-800/80 bg-black/20 px-2 py-1.5 text-[11px] leading-relaxed text-zinc-300">
                  {segment.explanation || segment.reason || "Included by the prompt graph."}
                </div>
                <div className="mt-1.5 grid gap-1 text-[11px] text-zinc-500">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <SlidersHorizontal size={11} className="shrink-0 text-cyan-300/80" />
                    <span className="min-w-0 truncate">{detailLine(segment)}</span>
                  </div>
                  <div className="flex min-w-0 items-center gap-1.5">
                    <ShieldCheck size={11} className="shrink-0 text-emerald-300/80" />
                    <span className="min-w-0 truncate">{safetyLine(segment)}</span>
                  </div>
                  {(() => {
                    const signal = signalLine(segment);
                    if (!signal) return null;
                    return (
                      <div className="flex min-w-0 items-center gap-1.5">
                        {signal.kind === "tool" ? <Wrench size={11} className="shrink-0 text-violet-300/80" /> : <Sparkles size={11} className="shrink-0 text-violet-300/80" />}
                        <span className="min-w-0 truncate">{signal.text}</span>
                      </div>
                    );
                  })()}
                </div>
                <div className="mt-1 truncate font-mono text-[10px] text-zinc-600">{segment.source || segment.source_type}</div>
                {(segment.text || segment.preview) && (
                  <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/25 p-2 font-mono text-[11px] leading-relaxed text-zinc-300">
                    {segment.text || segment.preview}
                  </pre>
                )}
              </div>
            ))}
          </div>
          {!segments.length && <div className="rounded-md border border-dashed border-zinc-800 px-3 py-4 text-center text-xs text-zinc-500">No prompt usage segments were recorded.</div>}
        </div>
      )}
    </div>
  );
}
