import {
  AlertTriangle,
  Bot,
  CircleDollarSign,
  Clock3,
  Cpu,
  Globe2,
  KeyRound,
  Pause,
  Play,
  RotateCw,
  Square,
  Wrench,
} from "lucide-react";

import type { AgentLifecycleAction, AgentRecord } from "../lib/api";
import { cn } from "../lib/cn";

export type AgentDisplayStats = {
  ticks: number;
  blockers: number;
  costUsd: number;
  tokens: number;
  toolCalls: number;
  failures: number;
};

export function agentDisplayStats(agent: AgentRecord): AgentDisplayStats {
  const metrics = agent.metrics ?? {};
  return {
    ticks: Number(metrics.ticks ?? 0),
    blockers: agent.blockers?.length ?? 0,
    costUsd: Number(metrics.cost_usd ?? 0),
    tokens: metrics.tokens === undefined
      ? Number(metrics.input_tokens ?? 0) + Number(metrics.output_tokens ?? 0)
      : Number(metrics.tokens ?? 0),
    toolCalls: Number(metrics.tool_calls ?? 0),
    failures: Number(metrics.failures ?? 0),
  };
}

export function formatCompactNumber(value: number): string {
  if (!Number.isFinite(value)) return "0";
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(Math.round(value));
}

export function statusTone(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === "running" || normalized === "scheduled") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
  if (normalized === "waiting_approval" || normalized === "blocked") return "border-amber-500/30 bg-amber-500/10 text-amber-200";
  if (normalized === "failed") return "border-red-500/30 bg-red-500/10 text-red-200";
  if (normalized === "paused") return "border-sky-500/30 bg-sky-500/10 text-sky-200";
  return "border-zinc-800 bg-zinc-900 text-zinc-400";
}

function formatCost(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "$0.00";
  return `$${value.toFixed(value >= 10 ? 1 : 2)}`;
}

function formatWhen(value: AgentRecord["last_tick_at"]): string {
  if (!value) return "never";
  const time = typeof value === "number" ? value : Date.parse(String(value));
  if (!Number.isFinite(time)) return String(value);
  const minutes = Math.max(0, Math.round((Date.now() - time) / 60_000));
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0 border-t border-zinc-800 px-3 py-2">
      <div className="truncate text-[10px] uppercase text-zinc-600">{label}</div>
      <div className="mt-0.5 truncate text-sm font-medium text-zinc-200">{value}</div>
    </div>
  );
}

export function AgentCard({
  agent,
  selected = false,
  onSelect,
  onLifecycleAction,
  onOpenBrowser,
  onOpenApprovals,
}: {
  agent: AgentRecord;
  selected?: boolean;
  onSelect?: (agent: AgentRecord) => void;
  onLifecycleAction?: (agent: AgentRecord, action: AgentLifecycleAction) => void;
  onOpenBrowser?: (agent: AgentRecord) => void;
  onOpenApprovals?: (agent: AgentRecord) => void;
}) {
  const stats = agentDisplayStats(agent);
  const running = agent.status === "running" || agent.status === "scheduled";
  const pendingApproval = agent.status === "waiting_approval" || Number(agent.metrics?.approvals_pending ?? 0) > 0;
  const tools = agent.tools ?? agent.tool_policy?.allowed_tools ?? [];

  return (
    <article
      className={cn(
        "min-w-0 overflow-hidden rounded-lg border bg-zinc-950/60 transition-colors",
        selected ? "border-emerald-500/40" : "border-zinc-800",
      )}
    >
      <button
        type="button"
        onClick={() => onSelect?.(agent)}
        className="flex w-full items-start gap-3 px-3 py-3 text-left hover:bg-zinc-900/70"
      >
        <span className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-400">
          <Bot size={16} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="truncate text-sm font-semibold text-zinc-100">{agent.name}</span>
            <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-medium", statusTone(agent.status))}>
              {agent.status}
            </span>
          </span>
          <span className="mt-1 block truncate text-[11px] text-zinc-500">
            {agent.profile_id || "profile"} · {agent.role || "role"}
          </span>
        </span>
      </button>

      <div className="grid grid-cols-2 border-t border-zinc-800 text-[11px] text-zinc-500 md:grid-cols-4">
        <div className="flex min-w-0 items-center gap-1.5 px-3 py-2">
          <Cpu size={13} className="flex-shrink-0" />
          <span className="truncate">{agent.model || "default"}</span>
        </div>
        <div className="flex min-w-0 items-center gap-1.5 px-3 py-2">
          <KeyRound size={13} className="flex-shrink-0" />
          <span className="truncate">{agent.api_key_id || agent.provider_id || "default"}</span>
        </div>
        <div className="flex min-w-0 items-center gap-1.5 px-3 py-2">
          <Globe2 size={13} className="flex-shrink-0" />
          <span className="truncate">{agent.browser_enabled ? agent.browser_profile_id || "default" : "off"}</span>
        </div>
        <div className="flex min-w-0 items-center gap-1.5 px-3 py-2">
          <Clock3 size={13} className="flex-shrink-0" />
          <span className="truncate">tick {formatWhen(agent.last_tick_at ?? agent.metrics?.last_tick_at)}</span>
        </div>
      </div>

      <div className="grid grid-cols-3">
        <Metric label="ticks" value={formatCompactNumber(stats.ticks)} />
        <Metric label="blockers" value={formatCompactNumber(stats.blockers)} />
        <Metric label="cost" value={formatCost(stats.costUsd)} />
        <Metric label="tokens" value={formatCompactNumber(stats.tokens)} />
        <Metric label="tools" value={formatCompactNumber(stats.toolCalls)} />
        <Metric label="failures" value={formatCompactNumber(stats.failures)} />
      </div>

      <div className="flex min-w-0 flex-wrap items-center gap-1 border-t border-zinc-800 px-3 py-2">
        {tools.slice(0, 5).map((tool) => (
          <span key={tool} className="inline-flex max-w-[140px] items-center gap-1 rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 text-[10px] text-zinc-400">
            <Wrench size={10} className="flex-shrink-0" />
            <span className="truncate">{tool}</span>
          </span>
        ))}
        {tools.length > 5 && <span className="text-[10px] text-zinc-600">+{tools.length - 5}</span>}
      </div>

      {(agent.blockers?.length || pendingApproval) && (
        <div className="border-t border-zinc-800 px-3 py-2 text-[11px] text-amber-200">
          <div className="flex min-w-0 items-center gap-1.5">
            <AlertTriangle size={13} className="flex-shrink-0" />
            <span className="truncate">{agent.blockers?.[0] || "Approval pending"}</span>
          </div>
        </div>
      )}

      <footer className="flex flex-wrap justify-end gap-2 border-t border-zinc-800 px-3 py-2">
        {onOpenApprovals && (
          <button
            type="button"
            onClick={() => onOpenApprovals(agent)}
            className="flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800"
            title="Open approvals"
          >
            <AlertTriangle size={13} /> Approvals
          </button>
        )}
        {onOpenBrowser && (
          <button
            type="button"
            onClick={() => onOpenBrowser(agent)}
            className="flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800"
            title="Open browser viewer"
          >
            <Globe2 size={13} /> Browser
          </button>
        )}
        <button
          type="button"
          onClick={() => onLifecycleAction?.(agent, running ? "pause" : "resume")}
          className="flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800"
          title={running ? "Pause agent" : "Resume agent"}
        >
          {running ? <Pause size={13} /> : <Play size={13} />}
          {running ? "Pause" : "Resume"}
        </button>
        <button
          type="button"
          onClick={() => onLifecycleAction?.(agent, "tick")}
          className="flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800"
          title="Trigger one tick"
        >
          <RotateCw size={13} /> Tick
        </button>
        <button
          type="button"
          onClick={() => onLifecycleAction?.(agent, "stop")}
          className="flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800"
          title="Stop agent"
        >
          <Square size={12} /> Stop
        </button>
      </footer>
    </article>
  );
}
