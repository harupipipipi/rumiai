import { useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, Bot, CircleDollarSign, Plus, RefreshCw, ShieldCheck, Timer, Wrench } from "lucide-react";

import { AgentCard, agentDisplayStats, formatCompactNumber } from "./AgentCard";
import type { AgentLifecycleAction, AgentRecord } from "../lib/api";
import { cn } from "../lib/cn";

export type AgentFleetSummary = {
  total: number;
  running: number;
  waitingApproval: number;
  blocked: number;
  failures: number;
  tokens: number;
  costUsd: number;
  toolCalls: number;
};

export function summarizeAgentFleet(agents: AgentRecord[]): AgentFleetSummary {
  return agents.reduce<AgentFleetSummary>(
    (summary, agent) => {
      const stats = agentDisplayStats(agent);
      const status = agent.status.toLowerCase();
      summary.total += 1;
      if (status === "running" || status === "scheduled") summary.running += 1;
      if (status === "waiting_approval") summary.waitingApproval += 1;
      if (status === "blocked") summary.blocked += 1;
      summary.failures += stats.failures;
      summary.tokens += stats.tokens;
      summary.costUsd += stats.costUsd;
      summary.toolCalls += stats.toolCalls;
      return summary;
    },
    { total: 0, running: 0, waitingApproval: 0, blocked: 0, failures: 0, tokens: 0, costUsd: 0, toolCalls: 0 },
  );
}

function formatCost(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return "$0.00";
  return `$${value.toFixed(value >= 10 ? 1 : 2)}`;
}

function StatPill({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex h-10 min-w-[116px] items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950/60 px-3">
      <span className="text-zinc-500">{icon}</span>
      <span className="min-w-0">
        <span className="block truncate text-[10px] uppercase text-zinc-600">{label}</span>
        <span className="block truncate text-sm font-semibold text-zinc-200">{value}</span>
      </span>
    </div>
  );
}

export function AgentDashboard({
  agents,
  loading = false,
  error = "",
  selectedId,
  onSelectAgent,
  onRefresh,
  onCreateAgent,
  onLifecycleAction,
  onOpenBrowser,
  onOpenApprovals,
  onEditAgent,
}: {
  agents: AgentRecord[];
  loading?: boolean;
  error?: string;
  selectedId?: string | null;
  onSelectAgent?: (agent: AgentRecord) => void;
  onRefresh?: () => void;
  onCreateAgent?: () => void;
  onLifecycleAction?: (agent: AgentRecord, action: AgentLifecycleAction) => void;
  onOpenBrowser?: (agent: AgentRecord) => void;
  onOpenApprovals?: (agent: AgentRecord) => void;
  onEditAgent?: (agent: AgentRecord) => void;
}) {
  const [statusFilter, setStatusFilter] = useState("all");
  const [query, setQuery] = useState("");
  const summary = useMemo(() => summarizeAgentFleet(agents), [agents]);
  const statuses = useMemo(() => ["all", ...Array.from(new Set(agents.map((agent) => agent.status)))], [agents]);
  const filteredAgents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return agents.filter((agent) => {
      const matchesStatus = statusFilter === "all" || agent.status === statusFilter;
      const haystack = `${agent.name} ${agent.profile_id ?? ""} ${agent.role ?? ""} ${agent.model ?? ""}`.toLowerCase();
      return matchesStatus && (!normalizedQuery || haystack.includes(normalizedQuery));
    });
  }, [agents, query, statusFilter]);

  return (
    <section className="flex h-full min-h-0 flex-col bg-[#09090b] text-zinc-100">
      <header className="border-b border-zinc-800 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold">Agents</h2>
            <p className="mt-0.5 truncate text-[11px] text-zinc-500">
              {summary.running} running · {summary.waitingApproval} approvals · {summary.blocked} blocked
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                disabled={loading}
                className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                title="Refresh agents"
              >
                <RefreshCw size={14} /> Refresh
              </button>
            )}
            {onCreateAgent && (
              <button
                type="button"
                onClick={onCreateAgent}
                className="flex h-8 items-center gap-1.5 rounded-md bg-zinc-100 px-2.5 text-xs font-semibold text-zinc-950 hover:bg-white"
                title="Create agent"
              >
                <Plus size={14} /> New
              </button>
            )}
          </div>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <StatPill icon={<Bot size={15} />} label="total" value={String(summary.total)} />
          <StatPill icon={<Timer size={15} />} label="tokens" value={formatCompactNumber(summary.tokens)} />
          <StatPill icon={<Wrench size={15} />} label="tool calls" value={formatCompactNumber(summary.toolCalls)} />
          <StatPill icon={<CircleDollarSign size={15} />} label="cost" value={formatCost(summary.costUsd)} />
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter agents"
            className="h-8 min-w-[180px] flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-xs text-zinc-100 outline-none focus:border-zinc-600"
          />
          <div className="flex max-w-full gap-1 overflow-x-auto">
            {statuses.map((status) => (
              <button
                key={status}
                type="button"
                onClick={() => setStatusFilter(status)}
                className={cn(
                  "h-8 flex-shrink-0 rounded-md border px-2.5 text-xs font-medium transition-colors",
                  statusFilter === status
                    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
                    : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200",
                )}
              >
                {status}
              </button>
            ))}
          </div>
        </div>
      </header>

      {error && (
        <div className="mx-4 mt-3 flex items-center gap-2 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          <AlertTriangle size={14} /> <span className="min-w-0 truncate">{error}</span>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {filteredAgents.length > 0 ? (
          <div className="grid gap-3 xl:grid-cols-2">
            {filteredAgents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                selected={agent.id === selectedId}
                onSelect={onSelectAgent}
                onLifecycleAction={onLifecycleAction}
                onOpenBrowser={onOpenBrowser}
                onOpenApprovals={onOpenApprovals}
                onEditAgent={onEditAgent}
              />
            ))}
          </div>
        ) : (
          <div className="flex h-full min-h-[180px] items-center justify-center rounded-lg border border-dashed border-zinc-800 text-sm text-zinc-500">
            {loading ? "Loading agents..." : "No agents match the current filter."}
          </div>
        )}
      </div>

      {(summary.waitingApproval > 0 || summary.blocked > 0 || summary.failures > 0) && (
        <footer className="flex flex-wrap gap-2 border-t border-zinc-800 px-4 py-2 text-[11px] text-zinc-500">
          <span className="inline-flex items-center gap-1 text-amber-200">
            <ShieldCheck size={13} /> {summary.waitingApproval} approval queues
          </span>
          <span className="inline-flex items-center gap-1 text-amber-200">
            <AlertTriangle size={13} /> {summary.blocked} blockers
          </span>
          <span>{summary.failures} failures</span>
        </footer>
      )}
    </section>
  );
}
