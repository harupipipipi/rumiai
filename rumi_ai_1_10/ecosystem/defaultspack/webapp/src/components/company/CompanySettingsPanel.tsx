import { Save } from "lucide-react";
import { useEffect, useState } from "react";

function asBool(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

export function CompanySettingsPanel({
  settings,
  busy = false,
  onSave,
}: {
  settings: Record<string, unknown>;
  busy?: boolean;
  onSave?: (settings: Record<string, unknown>) => void;
}) {
  const [draft, setDraft] = useState(settings);

  useEffect(() => {
    setDraft(settings);
  }, [settings]);

  const update = (key: string, value: unknown) => setDraft((current) => ({ ...current, [key]: value }));

  return (
    <section className="space-y-2 p-2">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Settings</h4>
        {onSave && (
          <button
            type="button"
            onClick={() => onSave(draft)}
            disabled={busy}
            className="flex h-7 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-40"
          >
            <Save size={12} />
            Save
          </button>
        )}
      </div>

      <div className="space-y-2">
        <label className="flex items-center justify-between gap-3 rounded-md border border-zinc-800/70 bg-zinc-950/40 px-2 py-1.5">
          <span className="text-[11px] text-zinc-400">Queue tasks</span>
          <select
            value={String(draft.task_policy ?? "queued")}
            onChange={(event) => update("task_policy", event.target.value)}
            className="max-w-[120px] bg-transparent text-[11px] text-zinc-200 outline-none"
          >
            <option className="bg-zinc-900" value="queued">queued</option>
            <option className="bg-zinc-900" value="manual">manual</option>
          </select>
        </label>

        <label className="flex items-center justify-between gap-3 rounded-md border border-zinc-800/70 bg-zinc-950/40 px-2 py-1.5">
          <span className="text-[11px] text-zinc-400">Dispatch policy</span>
          <span className="max-w-[130px] truncate font-mono text-[10px] text-zinc-500">
            {String(draft.dispatch_policy ?? "local_queue_only")}
          </span>
        </label>

        {[
          ["normal_status_silent", "Quiet normal status"],
          ["mentions_create_tasks", "Mentions create tasks"],
          ["direct_tool_execution", "Direct tool execution"],
        ].map(([key, label]) => (
          <label key={key} className="flex items-center justify-between gap-3 rounded-md border border-zinc-800/70 bg-zinc-950/40 px-2 py-1.5">
            <span className="text-[11px] text-zinc-400">{label}</span>
            <input
              type="checkbox"
              checked={asBool(draft[key], key !== "direct_tool_execution")}
              onChange={(event) => update(key, event.target.checked)}
              className="h-4 w-4 accent-emerald-500"
            />
          </label>
        ))}
      </div>
    </section>
  );
}
