import { Bot, Wrench } from "lucide-react";

import type { CompanyAgent } from "../../lib/api";

export function CompanyAgentList({ agents }: { agents: CompanyAgent[] }) {
  return (
    <section className="space-y-2 p-2">
      <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Agents</h4>
      <div className="space-y-1.5">
        {agents.map((agent) => (
          <div key={agent.agent_id} className="rounded-md border border-zinc-800/70 bg-zinc-950/40 px-2 py-1.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <Bot size={13} className="flex-shrink-0 text-zinc-500" />
                <span className="truncate text-[12px] font-medium text-zinc-200">
                  {agent.display_name || agent.agent_name || agent.agent_id}
                </span>
              </div>
              <span className="flex-shrink-0 rounded border border-zinc-800 px-1.5 py-0.5 text-[9px] text-zinc-500">
                {agent.status ?? "idle"}
              </span>
            </div>
            <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-zinc-500">
              <span className="truncate font-mono">{agent.model ?? "stub/default"}</span>
              <span className="flex flex-shrink-0 items-center gap-1">
                <Wrench size={10} />
                {(agent.allowed_tools ?? []).length}
              </span>
            </div>
            {agent.aliases && agent.aliases.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {agent.aliases.slice(0, 4).map((alias) => (
                  <span key={alias} className="rounded border border-zinc-800 bg-zinc-900/60 px-1 py-0.5 text-[9px] text-zinc-500">
                    @{alias}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
        {agents.length === 0 && (
          <div className="rounded-md border border-zinc-800/70 bg-zinc-950/40 px-2 py-2 text-[11px] text-zinc-500">
            No agents configured.
          </div>
        )}
      </div>
    </section>
  );
}
