import { Plus, Trash2 } from "lucide-react";

import {
  REGISTERED_SLASH_COMMAND_ACTIONS,
  normalizeRegisteredSlashCommandAliases,
  normalizeRegisteredSlashCommandName,
  type RegisteredSlashCommandActionId,
  type RegisteredSlashCommandRecord,
} from "../../../lib/registeredSlashCommands";
import type { SettingsFieldRendererProps } from "../fieldRendererRegistry";
import { SettingsFieldShell } from "./settingsFieldRendererUtils";

type SlashCommandDraft = {
  name: string;
  action: RegisteredSlashCommandActionId;
  aliases: string;
  description: string;
  enabled: boolean;
};

function recordFromUnknown(value: unknown): SlashCommandDraft | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  const action = String(record.action ?? "toggle_yolo") as RegisteredSlashCommandActionId;
  const hasAction = REGISTERED_SLASH_COMMAND_ACTIONS.some((item) => item.id === action);
  return {
    name: normalizeRegisteredSlashCommandName(record.name ?? record.command ?? record.id),
    action: hasAction ? action : "toggle_yolo",
    aliases: normalizeRegisteredSlashCommandAliases(record.aliases).join(", "),
    description: String(record.description ?? "").trim(),
    enabled: record.enabled !== false,
  };
}

function normalizeDrafts(value: unknown): SlashCommandDraft[] {
  return (Array.isArray(value) ? value : [])
    .map(recordFromUnknown)
    .filter((item): item is SlashCommandDraft => Boolean(item));
}

function serializeDrafts(drafts: SlashCommandDraft[]): RegisteredSlashCommandRecord[] {
  return drafts
    .map((draft) => ({
      name: normalizeRegisteredSlashCommandName(draft.name),
      action: draft.action,
      aliases: normalizeRegisteredSlashCommandAliases(draft.aliases),
      description: draft.description.trim(),
      enabled: draft.enabled,
    }))
    .filter((item) => item.name);
}

export function BuiltinSlashCommandsRenderer({ sectionId, field, value, onChange }: SettingsFieldRendererProps) {
  const drafts = normalizeDrafts(value ?? field.default);
  const updateDraft = (index: number, patch: Partial<SlashCommandDraft>) => {
    const next = drafts.map((draft, draftIndex) => (
      draftIndex === index ? { ...draft, ...patch } : draft
    ));
    onChange(sectionId, field.id, serializeDrafts(next));
  };
  const removeDraft = (index: number) => {
    onChange(sectionId, field.id, serializeDrafts(drafts.filter((_, draftIndex) => draftIndex !== index)));
  };
  const addDraft = () => {
    onChange(sectionId, field.id, serializeDrafts([
      ...drafts,
      { name: "", action: "toggle_yolo", aliases: "", description: "", enabled: true },
    ]));
  };
  const addYolo = () => {
    const hasYolo = drafts.some((draft) => normalizeRegisteredSlashCommandName(draft.name) === "yolo");
    if (hasYolo) return;
    onChange(sectionId, field.id, serializeDrafts([
      ...drafts,
      { name: "yolo", action: "toggle_yolo", aliases: "", description: "会話で /yolo と打つとYOLOを切り替えます。", enabled: true },
    ]));
  };

  return (
    <SettingsFieldShell field={field}>
      <div data-settings-renderer="slash_commands" className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={addDraft}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-zinc-700 bg-zinc-900 px-2.5 text-xs text-zinc-200 hover:bg-zinc-800"
          >
            <Plus size={13} />
            Add
          </button>
          <button
            type="button"
            onClick={addYolo}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 text-xs text-amber-200 hover:bg-amber-500/15"
          >
            /yolo
          </button>
        </div>
        {drafts.length === 0 ? (
          <p className="rounded-md border border-dashed border-zinc-800 px-3 py-2 text-xs text-zinc-500">
            まだ登録されていません。Add または /yolo から追加できます。
          </p>
        ) : (
          <div className="space-y-2">
            {drafts.map((draft, index) => (
              <div key={`${index}-${draft.name || "new"}`} className="grid gap-2 rounded-md border border-zinc-800 bg-zinc-950/50 p-2 md:grid-cols-[minmax(120px,0.9fr)_minmax(160px,1fr)_minmax(140px,1fr)_32px]">
                <label className="min-w-0 space-y-1">
                  <span className="block text-[11px] text-zinc-500">Command</span>
                  <div className="flex min-w-0 items-center rounded-md border border-zinc-800 bg-zinc-900 px-2 focus-within:border-zinc-600">
                    <span className="text-zinc-500">/</span>
                    <input
                      value={draft.name}
                      onChange={(event) => updateDraft(index, { name: event.target.value })}
                      placeholder="yolo"
                      className="h-8 min-w-0 flex-1 bg-transparent px-1 text-sm text-zinc-200 outline-none placeholder:text-zinc-600"
                    />
                  </div>
                </label>
                <label className="min-w-0 space-y-1">
                  <span className="block text-[11px] text-zinc-500">Action</span>
                  <select
                    value={draft.action}
                    onChange={(event) => updateDraft(index, { action: event.target.value as RegisteredSlashCommandActionId })}
                    className="h-8 w-full rounded-md border border-zinc-800 bg-zinc-900 px-2 text-sm text-zinc-200 outline-none"
                  >
                    {REGISTERED_SLASH_COMMAND_ACTIONS.map((action) => (
                      <option key={action.id} value={action.id} className="bg-zinc-900">
                        {action.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="min-w-0 space-y-1">
                  <span className="block text-[11px] text-zinc-500">Aliases</span>
                  <input
                    value={draft.aliases}
                    onChange={(event) => updateDraft(index, { aliases: event.target.value })}
                    placeholder="go, run"
                    className="h-8 w-full rounded-md border border-zinc-800 bg-zinc-900 px-2 text-sm text-zinc-200 outline-none placeholder:text-zinc-600"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => removeDraft(index)}
                  className="mt-5 flex h-8 w-8 items-center justify-center rounded-md border border-zinc-800 text-zinc-500 hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-200"
                  title="Remove command"
                  aria-label="Remove command"
                >
                  <Trash2 size={14} />
                </button>
                <label className="flex items-center gap-2 md:col-span-4">
                  <input
                    type="checkbox"
                    checked={draft.enabled}
                    onChange={(event) => updateDraft(index, { enabled: event.target.checked })}
                    className="h-4 w-4 accent-emerald-500"
                  />
                  <span className="text-xs text-zinc-400">Enabled</span>
                </label>
              </div>
            ))}
          </div>
        )}
      </div>
    </SettingsFieldShell>
  );
}
