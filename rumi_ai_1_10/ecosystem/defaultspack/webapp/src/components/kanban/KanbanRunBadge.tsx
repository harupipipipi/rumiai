import { AlertTriangle, CheckCircle2, CircleDot, GitBranch, PlayCircle, Timer, XCircle } from "lucide-react";

import { cn } from "../../lib/cn";

function statusTone(status: string | null | undefined): {
  label: string;
  className: string;
  icon: typeof CircleDot;
} {
  const normalized = String(status || "idle").trim().toLowerCase();
  if (["running", "in_progress", "started"].includes(normalized)) {
    return { label: "running", className: "border-sky-500/30 bg-sky-500/10 text-sky-200", icon: PlayCircle };
  }
  if (["ready", "waiting_review", "waiting_approval"].includes(normalized)) {
    return { label: normalized === "ready" ? "ready" : "review", className: "border-amber-500/30 bg-amber-500/10 text-amber-200", icon: Timer };
  }
  if (["applied", "completed", "done", "success"].includes(normalized)) {
    return { label: normalized === "success" ? "done" : normalized, className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200", icon: CheckCircle2 };
  }
  if (["failed", "error", "blocked", "stale"].includes(normalized)) {
    return { label: normalized, className: "border-red-500/30 bg-red-500/10 text-red-200", icon: XCircle };
  }
  if (normalized === "dismissed") {
    return { label: "dismissed", className: "border-zinc-700 bg-zinc-900 text-zinc-400", icon: AlertTriangle };
  }
  return { label: "idle", className: "border-zinc-800 bg-zinc-950/80 text-zinc-500", icon: CircleDot };
}

export function KanbanRunBadge({
  status,
  branch,
  compact = false,
}: {
  status?: string | null;
  branch?: string | null;
  compact?: boolean;
}) {
  const tone = statusTone(status);
  const StatusIcon = tone.icon;

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      <span className={cn(
        "inline-flex min-w-0 items-center gap-1 rounded-full border px-1.5 py-0.5 font-medium",
        compact ? "text-[9px]" : "text-[10px]",
        tone.className,
      )}>
        <StatusIcon size={compact ? 10 : 11} className="shrink-0" />
        <span className="truncate">{tone.label}</span>
      </span>
      {branch && (
        <span className={cn(
          "inline-flex min-w-0 items-center gap-1 rounded-full border border-zinc-800 bg-zinc-950/60 px-1.5 py-0.5 text-zinc-500",
          compact ? "text-[9px]" : "text-[10px]",
        )}>
          <GitBranch size={compact ? 10 : 11} className="shrink-0" />
          <span className="max-w-28 truncate">{branch}</span>
        </span>
      )}
    </div>
  );
}
