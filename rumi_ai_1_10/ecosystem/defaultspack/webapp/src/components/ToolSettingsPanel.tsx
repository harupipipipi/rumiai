import { EyeOff, Search, Settings2, ShieldAlert, Wrench } from "lucide-react";
import { useMemo, useState } from "react";

import type { SidebarItem } from "../lib/api";

function textHaystack(tool: SidebarItem): string {
  return [
    tool.id,
    tool.label,
    tool.description ?? "",
    ...(tool.tags ?? []),
    ...(tool.tool_info?.requires_model_capabilities ?? []),
    ...(tool.tool_info?.requires_input_modalities ?? []),
    ...(tool.tool_info?.requires_runtime_capabilities ?? []),
  ].join(" ").toLowerCase();
}

function chip(label: string, tone = "text-zinc-400 border-zinc-700") {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] ${tone}`}>
      {label}
    </span>
  );
}

export function ToolSettingsPanel({
  tools,
  disabledToolIds,
  hiddenToolIds,
  onSettingChange,
}: {
  tools: SidebarItem[];
  disabledToolIds: string[];
  hiddenToolIds: string[];
  onSettingChange: (sectionId: string, fieldId: string, value: unknown) => void;
}) {
  const [query, setQuery] = useState("");
  const disabledSet = useMemo(() => new Set(disabledToolIds), [disabledToolIds]);
  const hiddenSet = useMemo(() => new Set(hiddenToolIds), [hiddenToolIds]);
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return tools;
    return tools.filter((tool) => textHaystack(tool).includes(normalized));
  }, [query, tools]);

  const toggleId = (current: string[], id: string) => (
    current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
  );

  return (
    <div className="mb-4 rounded-xl border border-zinc-800 bg-zinc-950/50 p-3">
      <div className="mb-3 flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-300">
          <Settings2 size={15} />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-zinc-100">Tool details</p>
          <p className="text-xs text-zinc-500">検索、常時OFF、hidden、capability要件の確認。</p>
        </div>
      </div>
      <label className="mb-3 flex h-9 items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-3 text-xs text-zinc-500 focus-within:border-zinc-600">
        <Search size={14} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="tool / capability / tag で検索"
          className="min-w-0 flex-1 bg-transparent text-sm text-zinc-200 outline-none placeholder:text-zinc-600"
        />
      </label>
      <div className="space-y-2">
        {filtered.map((tool) => {
          const disabled = disabledSet.has(tool.id);
          const hidden = hiddenSet.has(tool.id);
          const info = tool.tool_info;
          return (
            <div key={tool.id} className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2.5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-zinc-100">{tool.label}</p>
                  {tool.description && <p className="mt-0.5 text-xs text-zinc-500">{tool.description}</p>}
                </div>
                <div className="flex flex-shrink-0 items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => onSettingChange("tools", "disabled_tool_ids", toggleId(disabledToolIds, tool.id))}
                    className={`rounded-lg border px-2 py-1 text-[11px] ${
                      disabled
                        ? "border-zinc-700 bg-zinc-900 text-zinc-300"
                        : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                    }`}
                  >
                    {disabled ? "OFF" : "ON"}
                  </button>
                  <button
                    type="button"
                    onClick={() => onSettingChange("tools", "hidden_tool_ids", toggleId(hiddenToolIds, tool.id))}
                    className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] ${
                      hidden
                        ? "border-zinc-700 bg-zinc-900 text-zinc-300"
                        : "border-zinc-800 bg-zinc-950 text-zinc-400"
                    }`}
                  >
                    <EyeOff size={11} />
                    {hidden ? "Hidden" : "Hide"}
                  </button>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {info?.requires_approval && chip("approval", "text-sky-300 border-sky-500/30")}
                {hidden && chip("hidden", "text-zinc-300 border-zinc-700")}
                {info?.attachment_policy && chip(`attach:${info.attachment_policy}`)}
                {(info?.requires_model_capabilities ?? []).map((value) => <span key={`model:${value}`}>{chip(value, "text-amber-200 border-amber-500/30")}</span>)}
                {(info?.requires_input_modalities ?? []).map((value) => <span key={`input:${value}`}>{chip(value, "text-emerald-200 border-emerald-500/30")}</span>)}
                {(info?.requires_runtime_capabilities ?? []).map((value) => <span key={`runtime:${value}`}>{chip(value, "text-cyan-200 border-cyan-500/30")}</span>)}
                {info?.setup_state?.status === "missing" && chip("setup required", "text-rose-300 border-rose-500/30")}
              </div>
              <details className="mt-2 rounded-lg border border-zinc-800 bg-black/20 px-3 py-2">
                <summary className="cursor-pointer text-[11px] text-zinc-500">Advanced</summary>
                <div className="mt-2 space-y-2 text-[11px] text-zinc-400">
                  {info?.approval_policy && (
                    <div className="flex items-start gap-2">
                      <ShieldAlert size={12} className="mt-0.5 flex-shrink-0 text-sky-300" />
                      <span>Approval policy: {info.approval_policy}</span>
                    </div>
                  )}
                  {info?.capability_requirements && (
                    <div className="flex items-start gap-2">
                      <Wrench size={12} className="mt-0.5 flex-shrink-0 text-zinc-500" />
                      <pre className="whitespace-pre-wrap font-mono text-[10px] text-zinc-500">
                        {JSON.stringify(info.capability_requirements, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </details>
            </div>
          );
        })}
      </div>
    </div>
  );
}
