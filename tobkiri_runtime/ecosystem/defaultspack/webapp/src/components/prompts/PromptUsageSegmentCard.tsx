import { Eye, FileText, Lock, ShieldCheck, SlidersHorizontal, Sparkles, ToggleLeft, ToggleRight, Wrench } from "lucide-react";

import type { PromptUsageSegment } from "../../lib/api";
import { cn } from "../../lib/cn";
import {
  activationLine,
  promptSegmentKindLabel,
  promptSegmentSignal,
  promptSegmentTitle,
  safetySummary,
  sourceLine,
  statusBadgeClass,
  statusTextClass,
  tokenText,
} from "./promptSegmentView";

type PromptUsageSegmentCardProps = {
  segment: PromptUsageSegment;
  variant?: "command" | "disclosure";
  busy?: boolean;
  onToggle?: (segment: PromptUsageSegment) => void;
  onInspect?: (promptId?: string) => void;
};

export function PromptUsageSegmentCard({
  segment,
  variant = "disclosure",
  busy = false,
  onToggle,
  onInspect,
}: PromptUsageSegmentCardProps) {
  const edgeId = String(segment.edge_id ?? "").trim();
  const canToggle = Boolean(edgeId) && segment.allow_disable !== false && Boolean(onToggle);
  const isActive = segment.status === "active";
  const signal = promptSegmentSignal(segment);
  const SignalIcon = signal?.kind === "tool" ? Wrench : Sparkles;
  const previewClass = variant === "command" ? "max-h-28" : "max-h-48";
  const title = promptSegmentTitle(segment);

  return (
    <div className={cn(
      variant === "command"
        ? "rounded-xl border border-zinc-800 bg-zinc-900/35 p-3"
        : "rounded-lg border border-zinc-800 bg-zinc-950/70 p-2",
    )}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className={cn(
              variant === "command"
                ? "text-[11px] font-semibold"
                : "rounded border px-1.5 py-0.5 text-[10px] font-medium",
              variant === "command" ? statusTextClass(segment.status) : statusBadgeClass(segment.status),
            )}>
              {segment.status ?? "available"}
            </span>
            <span className={cn("min-w-0 truncate font-semibold text-zinc-100", variant === "command" ? "text-sm" : "text-xs")}>
              {title}
            </span>
            {variant === "disclosure" && (
              <>
                <span className="rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">{promptSegmentKindLabel(segment)}</span>
                <span className="font-mono text-[10px] text-zinc-500">{tokenText(segment.tokens)}</span>
              </>
            )}
            {segment.allow_disable === false && variant === "disclosure" && <Lock size={11} className="text-zinc-500" />}
            {segment.editable && variant === "disclosure" && <SlidersHorizontal size={11} className="text-cyan-300" />}
          </div>
          {variant === "command" && (
            <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-zinc-500">
              <span>{promptSegmentKindLabel(segment)}</span>
              <span>{tokenText(segment.tokens)}</span>
              <span className="max-w-full truncate font-mono">{segment.source || segment.source_type}</span>
            </div>
          )}
        </div>
        {(onToggle || onInspect) && (
          <div className="flex shrink-0 items-center gap-1">
            {onToggle && (
              <button
                type="button"
                disabled={!canToggle || busy}
                onClick={() => onToggle(segment)}
                className={cn(
                  "rounded-md p-1.5",
                  canToggle ? "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100" : "cursor-not-allowed text-zinc-700",
                )}
                title={canToggle ? (isActive ? "Disable prompt segment" : "Enable prompt segment") : "This segment cannot be disabled"}
                aria-label={canToggle ? (isActive ? "Disable prompt segment" : "Enable prompt segment") : "Prompt segment cannot be disabled"}
              >
                {canToggle ? (isActive ? <ToggleRight size={17} /> : <ToggleLeft size={17} />) : <Lock size={15} />}
              </button>
            )}
            {onInspect && (
              <button
                type="button"
                onClick={() => onInspect(segment.prompt_id || segment.id)}
                className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-cyan-200"
                aria-label="Inspect prompt in Prompt Studio"
              >
                <Eye size={15} />
              </button>
            )}
          </div>
        )}
      </div>
      <div className={cn(
        "rounded-lg border border-zinc-800/80 bg-black/20 leading-relaxed text-zinc-300",
        variant === "command" ? "mt-2 px-2.5 py-2 text-[11px]" : "mt-1 px-2 py-1.5 text-[11px]",
      )}>
        {segment.explanation || segment.reason || "Included by the prompt graph."}
      </div>
      <div className={cn("grid text-zinc-500", variant === "command" ? "mt-2 gap-1.5 text-[11px]" : "mt-1.5 gap-1 text-[11px]")}>
        <div className="flex min-w-0 items-center gap-2">
          <SlidersHorizontal size={variant === "command" ? 12 : 11} className="shrink-0 text-cyan-300/80" />
          <span className="min-w-0 truncate">{activationLine(segment)}</span>
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <FileText size={variant === "command" ? 12 : 11} className="shrink-0 text-zinc-500" />
          <span className="min-w-0 truncate">{sourceLine(segment)}</span>
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <ShieldCheck size={variant === "command" ? 12 : 11} className="shrink-0 text-emerald-300/80" />
          <span className="min-w-0 truncate">{safetySummary(segment)}</span>
        </div>
        {signal && (
          <div className="flex min-w-0 items-center gap-2">
            <SignalIcon size={variant === "command" ? 12 : 11} className="shrink-0 text-violet-300/80" />
            <span className="min-w-0 truncate">{signal.label}: {signal.text}</span>
          </div>
        )}
      </div>
      {variant === "disclosure" && <div className="mt-1 truncate font-mono text-[10px] text-zinc-600">{segment.source || segment.source_type}</div>}
      {(segment.text || segment.preview) && (
        <pre className={cn(
          "mt-2 overflow-auto whitespace-pre-wrap border border-zinc-800 bg-black/25 p-2 font-mono text-[11px] leading-relaxed text-zinc-300",
          variant === "command" ? "rounded-lg" : "rounded-md",
          previewClass,
        )}>
          {segment.text || segment.preview}
        </pre>
      )}
    </div>
  );
}
