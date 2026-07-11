import { Archive, ClipboardList, Plus, RotateCcw, Search, Send, X } from "lucide-react";
import { useMemo, useState } from "react";

import type { CompanyAgent, CompanyRunLink, CompanyTask } from "../../lib/api";
import { CompanyRunConversation } from "./CompanyRunConversation";

export const COMPANY_TASK_STATUSES = [
  "queued",
  "assigned",
  "running",
  "waiting_approval",
  "blocked",
  "completed",
  "done",
  "cancelled",
  "failed",
] as const;

function taskStatus(task: Pick<CompanyTask, "status">): string {
  return String(task.status || "queued");
}

export function companyTaskStatusOptions(currentStatus: string): string[] {
  const normalized = String(currentStatus || "queued").trim() || "queued";
  return [
    ...COMPANY_TASK_STATUSES,
    ...(!COMPANY_TASK_STATUSES.includes(normalized as typeof COMPANY_TASK_STATUSES[number])
      ? [normalized]
      : []),
  ];
}

export function archiveCompanyTaskUpdate(task: CompanyTask): Partial<CompanyTask> {
  const metadata = {
    ...(task.metadata ?? {}),
    archived_from_status: taskStatus(task),
    archived_from_company_tasks_ui: true,
  };
  return { status: "cancelled", metadata };
}

export function restoreCompanyTaskUpdate(task: CompanyTask): Partial<CompanyTask> {
  const metadata = { ...(task.metadata ?? {}) };
  const previousStatus = typeof metadata.archived_from_status === "string"
    ? metadata.archived_from_status.trim()
    : "";
  delete metadata.archived_from_status;
  delete metadata.archived_from_company_tasks_ui;
  return {
    status: previousStatus && previousStatus !== "cancelled" ? previousStatus : "queued",
    metadata,
  };
}

export function CompanyTaskBoard({
  tasks,
  agents,
  runs = [],
  busy = false,
  onCreateTask,
  onCreateResearchTask,
  onUpdateTask,
  onDispatchTask,
}: {
  tasks: CompanyTask[];
  agents: CompanyAgent[];
  runs?: CompanyRunLink[];
  busy?: boolean;
  onCreateTask?: (title: string, targetAgentIds: string[]) => void;
  onCreateResearchTask?: (query: string, targetAgentIds: string[]) => void;
  onUpdateTask?: (taskId: string, updates: Partial<CompanyTask>) => void;
  onDispatchTask?: (taskId: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [targetAgentId, setTargetAgentId] = useState("");
  const [archiveCandidateId, setArchiveCandidateId] = useState<string | null>(null);
  const grouped = useMemo(() => {
    const map = new Map<string, CompanyTask[]>();
    for (const task of tasks) {
      const status = taskStatus(task);
      map.set(status, [...(map.get(status) ?? []), task]);
    }
    return map;
  }, [tasks]);
  const latestRunByTaskId = useMemo(() => {
    const map = new Map<string, CompanyRunLink>();
    for (const run of runs) {
      const taskId = String(run.task_id || "");
      if (taskId && !map.has(taskId)) map.set(taskId, run);
    }
    return map;
  }, [runs]);
  const visibleStatuses = useMemo(
    () => [
      ...COMPANY_TASK_STATUSES,
      ...[...grouped.keys()].filter(
        (status) => !(COMPANY_TASK_STATUSES as readonly string[]).includes(status),
      ),
    ],
    [grouped],
  );

  return (
    <section className="space-y-2 p-2">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Delegated Tasks</h4>
        <span className="text-[10px] text-zinc-600">{tasks.length}</span>
      </div>

      {onCreateTask && (
        <form
          className={onCreateResearchTask ? "grid grid-cols-[minmax(0,1fr)_92px_28px_28px] gap-1.5" : "grid grid-cols-[minmax(0,1fr)_92px_28px] gap-1.5"}
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
            placeholder="Ask an employee"
            className="h-8 min-w-0 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-[12px] text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
          />
          <select
            value={targetAgentId}
            onChange={(event) => setTargetAgentId(event.target.value)}
            disabled={busy}
            aria-label="Target employee"
            className="h-8 rounded-md border border-zinc-800 bg-zinc-950 px-1.5 text-[11px] text-zinc-300 outline-none"
          >
            <option value="">employee</option>
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
            aria-label="Create task"
          >
            <Plus size={13} />
          </button>
          {onCreateResearchTask && (
            <button
              type="button"
              disabled={busy || !title.trim()}
              onClick={() => {
                const query = title.trim();
                if (!query) return;
                onCreateResearchTask(query, targetAgentId ? [targetAgentId] : []);
                setTitle("");
              }}
              className="flex h-8 w-8 items-center justify-center rounded-md border border-sky-500/30 text-sky-300 hover:bg-sky-500/10 disabled:opacity-30"
              title="Deep research with DuckDuckGo"
              aria-label="Create deep research task"
            >
              <Search size={13} />
            </button>
          )}
        </form>
      )}

      <div className="space-y-2">
        {visibleStatuses.map((status) => {
          const items = grouped.get(status) ?? [];
          if (items.length === 0) return null;
          return (
            <div key={status} className="space-y-1">
              <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-zinc-600">
                <ClipboardList size={10} />
                <span>{status}</span>
                <span>{items.length}</span>
              </div>
              {items.map((task) => {
                const latestRun = latestRunByTaskId.get(task.id);
                const latestRunMessage = latestRun?.agent_run?.result_preview || latestRun?.agent_run?.error;
                const archiveConfirmationOpen = archiveCandidateId === task.id;
                const currentStatus = taskStatus(task);
                return (
                  <div key={task.id} className="rounded-md border border-zinc-800/70 bg-zinc-950/40 px-2 py-1.5">
                    <div className="flex items-start justify-between gap-2">
                      <p className="min-w-0 flex-1 text-[12px] font-medium leading-snug text-zinc-200">{task.title}</p>
                      <div className="flex flex-shrink-0 items-center gap-1">
                        {onDispatchTask && currentStatus === "queued" && (
                          <button
                            type="button"
                            onClick={() => onDispatchTask(task.id)}
                            disabled={busy}
                            className="flex h-7 w-7 items-center justify-center rounded border border-sky-500/30 text-sky-300 hover:bg-sky-500/10 disabled:opacity-40"
                            title="Dispatch task to agent"
                            aria-label={`Dispatch ${task.title}`}
                          >
                            <Send size={11} />
                          </button>
                        )}
                        {onUpdateTask && currentStatus === "cancelled" && (
                          <button
                            type="button"
                            onClick={() => onUpdateTask(task.id, restoreCompanyTaskUpdate(task))}
                            disabled={busy}
                            className="flex h-7 w-7 items-center justify-center rounded border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-40"
                            title="Restore archived task"
                            aria-label={`Restore ${task.title}`}
                          >
                            <RotateCcw size={11} />
                          </button>
                        )}
                        {onUpdateTask && currentStatus !== "cancelled" && !archiveConfirmationOpen && (
                          <button
                            type="button"
                            onClick={() => setArchiveCandidateId(task.id)}
                            disabled={busy}
                            className="flex h-7 w-7 items-center justify-center rounded border border-zinc-800 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200 disabled:opacity-40"
                            title="Archive task"
                            aria-label={`Archive ${task.title}`}
                          >
                            <Archive size={11} />
                          </button>
                        )}
                      </div>
                    </div>

                    {onUpdateTask && (
                      <label className="mt-2 grid grid-cols-[64px_minmax(0,1fr)] items-center gap-2 text-[10px] text-zinc-500">
                        <span>Status</span>
                        <select
                          aria-label={`Status for ${task.title}`}
                          value={currentStatus}
                          onChange={(event) => {
                            setArchiveCandidateId(null);
                            onUpdateTask(task.id, { status: event.target.value });
                          }}
                          disabled={busy}
                          className="h-7 min-w-0 rounded border border-zinc-800 bg-black/30 px-1.5 text-[11px] text-zinc-300 outline-none focus:border-zinc-600 disabled:opacity-40"
                        >
                          {companyTaskStatusOptions(currentStatus).map((candidate) => (
                            <option key={candidate} value={candidate}>{candidate}</option>
                          ))}
                        </select>
                      </label>
                    )}

                    {archiveConfirmationOpen && onUpdateTask && (
                      <div
                        role="group"
                        aria-label={`Confirm archive for ${task.title}`}
                        className="mt-2 rounded border border-amber-500/30 bg-amber-500/10 p-2"
                      >
                        <p className="text-[10px] leading-4 text-amber-100">
                          Archive this task? It remains in history and can be restored.
                        </p>
                        <div className="mt-1.5 flex justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => setArchiveCandidateId(null)}
                            disabled={busy}
                            className="flex h-7 items-center gap-1 rounded border border-zinc-700 px-2 text-[10px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
                          >
                            <X size={10} />
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              onUpdateTask(task.id, archiveCompanyTaskUpdate(task));
                              setArchiveCandidateId(null);
                            }}
                            disabled={busy}
                            className="flex h-7 items-center gap-1 rounded border border-amber-400/40 bg-amber-400/10 px-2 text-[10px] font-medium text-amber-100 hover:bg-amber-400/20 disabled:opacity-40"
                          >
                            <Archive size={10} />
                            Archive
                          </button>
                        </div>
                      </div>
                    )}

                    {task.target_agent_ids && task.target_agent_ids.length > 0 && (
                      <p className="mt-1 truncate text-[10px] text-zinc-500">{task.target_agent_ids.join(", ")}</p>
                    )}
                    {latestRun && (
                      <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-zinc-500">
                        <span className="truncate">{latestRun.agent_id}</span>
                        <span className="flex-shrink-0 rounded border border-zinc-800 px-1 py-0.5">{latestRun.agent_run?.status ?? latestRun.status}</span>
                      </div>
                    )}
                    {latestRun?.agent_run?.model && (
                      <p className="mt-1 truncate font-mono text-[10px] text-zinc-600">{latestRun.agent_run.model}</p>
                    )}
                    <CompanyRunConversation
                      messages={latestRun?.agent_run?.conversation}
                      fallback={latestRunMessage}
                      fallbackError={Boolean(latestRun?.agent_run?.error && !latestRun?.agent_run?.result_preview)}
                    />
                  </div>
                );
              })}
            </div>
          );
        })}
        {tasks.length === 0 && (
          <div className="rounded-md border border-zinc-800/70 bg-zinc-950/40 px-2 py-2 text-[11px] text-zinc-500">
            No delegated tasks.
          </div>
        )}
      </div>
    </section>
  );
}
