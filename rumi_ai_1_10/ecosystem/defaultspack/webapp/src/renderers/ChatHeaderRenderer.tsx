import { Bot, Hash, ShieldAlert, ShieldCheck } from "lucide-react";

import type { ChatHeaderRendererProps } from "./types";

function surfaceLabel(value: string | undefined): string {
  switch ((value ?? "").trim()) {
    case "mode_agent":
      return "Mode Agent";
    case "team_agent":
      return "Team Agent";
    case "fusion_agent":
      return "Fusion Agent";
    default:
      return "Agent";
  }
}

export function ChatHeaderRenderer({
  title,
  agentLabel,
  agentSurface,
  activationReason,
  reviewGateApproved = false,
}: ChatHeaderRendererProps) {
  const isAgentActive = Boolean(agentLabel && agentSurface && agentSurface !== "human");
  const readableReason = String(activationReason ?? "").trim().replace(/_/g, " ");

  return (
    <header className="min-h-11 border-b border-zinc-800/60 bg-[#09090b]/80 px-4 py-2 backdrop-blur-md rumi-layer-panel flex-shrink-0 rumi-anim-fade-down">
      <div className="flex min-w-0 items-start gap-2">
        <Hash size={14} className="text-zinc-600 flex-shrink-0" />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-medium text-zinc-200">{title}</h2>
          {isAgentActive && (
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <span
                className="inline-flex items-center gap-1 rounded-full border border-sky-400/20 bg-sky-400/10 px-2 py-0.5 text-[10px] font-medium text-sky-100"
                title={readableReason || undefined}
              >
                <Bot size={11} />
                {surfaceLabel(agentSurface)}: {agentLabel}
              </span>
              <span
                className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${
                  reviewGateApproved
                    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-100"
                    : "border-amber-500/20 bg-amber-500/10 text-amber-100"
                }`}
              >
                {reviewGateApproved ? <ShieldCheck size={11} /> : <ShieldAlert size={11} />}
                {reviewGateApproved ? "Review gate passed" : "Review gate pending"}
              </span>
              {readableReason && (
                <span className="rounded-full border border-zinc-800 bg-zinc-900/80 px-2 py-0.5 text-[10px] text-zinc-400">
                  {readableReason}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
