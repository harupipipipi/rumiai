import { Play, Terminal as TerminalIcon } from "lucide-react";
import { useState } from "react";

import { api, type CodingTerminalResponse } from "../../lib/api";
import { cn } from "../../lib/cn";

type TerminalLog = CodingTerminalResponse & {
  id: string;
};

function classificationTone(classification?: string): string {
  if (classification === "high" || classification === "blocked") return "text-red-300";
  if (classification === "medium") return "text-amber-300";
  return "text-emerald-300";
}

export function TerminalPanel({
  workspaceId,
  initialLogs = [],
}: {
  workspaceId?: string | null;
  initialLogs?: TerminalLog[];
}) {
  const [command, setCommand] = useState("git status");
  const [logs, setLogs] = useState<TerminalLog[]>(initialLogs);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    const nextCommand = command.trim();
    if (!nextCommand) return;
    setBusy(true);
    try {
      const result = await api.runTerminalCommand(nextCommand, { workspace_id: workspaceId, timeout: 30 });
      setLogs((items) => [{ ...result, id: `${Date.now()}:${nextCommand}` }, ...items].slice(0, 8));
    } catch (err) {
      setLogs((items) => [
        {
          id: `${Date.now()}:error`,
          command: nextCommand,
          classification: "error",
          risk_reasons: [err instanceof Error ? err.message : String(err)],
          approval_required: false,
          exit_code: null,
          stderr: err instanceof Error ? err.message : String(err),
        },
        ...items,
      ].slice(0, 8));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="border-b border-zinc-800/60 p-3" aria-label="Terminal">
      <div className="mb-2 flex items-center gap-2">
        <TerminalIcon size={14} className="text-emerald-300" />
        <h2 className="truncate text-xs font-semibold uppercase tracking-wide text-zinc-400">Terminal</h2>
      </div>

      <div className="flex items-center gap-1.5">
        <input
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void run();
          }}
          className="h-8 min-w-0 flex-1 rounded-md border border-zinc-800 bg-zinc-950/40 px-2 font-mono text-[11px] text-zinc-300 outline-none focus:border-zinc-600"
        />
        <button
          type="button"
          disabled={busy}
          onClick={() => void run()}
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-zinc-100 text-zinc-950 hover:bg-white disabled:opacity-40"
          title="Run command"
        >
          <Play size={13} />
        </button>
      </div>

      <div className="mt-2 space-y-2">
        {logs.map((log) => (
          <div key={log.id} className="rounded-md border border-zinc-800 bg-black/30 p-2">
            <div className="flex items-center justify-between gap-2">
              <code className="min-w-0 truncate text-[11px] text-zinc-200">{log.command}</code>
              <span className={cn("flex-shrink-0 text-[10px]", classificationTone(log.classification))}>
                {log.approval_required ? "approval" : log.classification || "low"}
              </span>
            </div>
            {log.risk_reasons?.length ? (
              <p className="mt-1 truncate text-[10px] text-zinc-600">{log.risk_reasons.join(", ")}</p>
            ) : null}
            <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap font-mono text-[10px] leading-relaxed text-zinc-500">
              {log.stdout || log.stderr || (log.approval_required ? "Approval required" : "")}
            </pre>
          </div>
        ))}
        {logs.length === 0 && <p className="py-3 text-center text-[11px] text-zinc-600">No terminal runs</p>}
      </div>
    </section>
  );
}
