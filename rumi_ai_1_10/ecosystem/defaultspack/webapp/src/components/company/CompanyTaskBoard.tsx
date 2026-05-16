import { ClipboardList, Plus } from "lucide-react";
import { useMemo, useState } from "react";

import type { CompanyAgent, CompanyTask } from "../../lib/api";

const STATUSES = ["queued", "running", "blocked", "done"] as const;

export function CompanyTaskBoard({
  tasks,
  agents,
  busy = false,
  onCreateTask,
  onUpdateTask,
}: {
  tasks: CompanyTask[];
  agents: CompanyAgent[];
  busy?: boolean;
  onCreateTask?: (title: string, targetAgentIds: string[]) => void;
  onUpdateTask?: (taskId: string, updates: Partial<CompanyTask>) => void;
}) {
  const [title, setTitle] = useState("");
  const [targetAgentId, setTargetAgentId] = useState("");
  const grouped = useMemo(() => {
    const map = new Map<string, CompanyTask[]>();
    for (const task of tasks) {
      const status = task.status || "queued";
      map.set(status, [...(map.get(status) ?? []), task]);
    }
    return map;
  }, [tasks]);

  return (
    <section className="space-y-2 p-2">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Tasks</h4>
        <span className="text-[10px] text-zinc-600">{tasks.length}</span>
      </div>

      {onCreateTask && (
        <form
          className="grid grid-cols-[minmax(0,1fr)_92px_28px] gap-1.5"
          onSubmit={(event) => {
            event.preventDefault();
            const cleanTitle = title.trim();
            if (!cleanTitle) return;
            onCreateTask(cleanTitle, targetAgentId ? [targetAgentId] : []);
            setTitle("");
          }}
        >
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            disabled={busy}
            placeholder="New task"
            className="h-8 min-w-0 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-[12px] text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
          />
          <select
            value={targetAgentId}
            onChange={(event) => setTargetAgentId(event.target.value)}
            disabled={busy}
            className="h-8 rounded-md border border-zinc-800 bg-zinc-950 px-1.5 text-[11px] text-zinc-300 outline-none"
          >
            <option value="">anyone</option>
            {agents.map((agent) => (
              <option key={agent.agent_id} value={agent.agent_id}>
                {agent.role_key || agent.agent_id}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={busy || !title.trim()}
            className="flex h-8 w-8 items-center justify-center rounded-md bg-zinc-100 text-zinc-950 hover:bg-white disabled:opacity-30"
            title="Create task"
          >
            <Plus size={13} />
          </button>
        </form>
      )}

      <div className="space-y-2">
        {STATUSES.map((status) => {
          const items = grouped.get(status) ?? [];
          if (items.length === 0) return null;
          return (
            <div key={status} className="space-y-1">
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-zinc-600">
                <ClipboardList size={10} />
                <span>{status}</span>
                <span>{items.length}</span>
              </div>
              {items.map((task) => (
                <div key={task.id} className="rounded-md border border-zinc-800/70 bg-zinc-950/40 px-2 py-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <p className="min-w-0 flex-1 text-[12px] font-medium leading-snug text-zinc-200">{task.title}</p>
                    {onUpdateTask && status !== "done" && (
                      <button
                        type="button"
                        onClick={() => onUpdateTask(task.id, { status: "done" })}
                        disabled={busy}
                        className="flex-shrink-0 rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-40"
                      >
                        done
                      </button>
                    )}
                  </div>
                  {task.target_agent_ids && task.target_agent_ids.length > 0 && (
                    <p className="mt-1 truncate text-[10px] text-zinc-500">{task.target_agent_ids.join(", ")}</p>
                  )}
                </div>
              ))}
            </div>
          );
        })}
        {tasks.length === 0 && (
          <div className="rounded-md border border-zinc-800/70 bg-zinc-950/40 px-2 py-2 text-[11px] text-zinc-500">
            No company tasks.
          </div>
        )}
      </div>
    </section>
  );
}
