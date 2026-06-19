import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Loader2, Search, X } from "lucide-react";

import { cn } from "../../../lib/cn";
import type { ModelSearchItem } from "../../../lib/api";
import {
  buildVisibleModelOptions,
  findSelectedModelOption,
  modelFieldOptionToModelSelectOption,
  modelSearchItemToModelSelectOption,
  modelSelectDisplay,
  type ModelSelectOption,
} from "../../../features/models/modelSelect";
import { settingsApiResources } from "../../../features/settings/resources/settingsApiResources";
import type { SettingsFieldRendererProps } from "../fieldRendererRegistry";
import { fieldOptions, modelSelectTargetFieldId, SettingsFieldShell } from "./settingsFieldRendererUtils";

export function SettingsModelSearchField({
  value,
  options,
  onChange,
  placeholder = "model/provider/特徴メモで検索",
}: {
  value: string;
  options: ModelSelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [remoteResults, setRemoteResults] = useState<ModelSearchItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const searchRequestSeq = useRef(0);
  const trimmedQuery = query.trim();
  const remoteOptions = useMemo(() => remoteResults.map(modelSearchItemToModelSelectOption), [remoteResults]);
  const selected = findSelectedModelOption(options, value, remoteOptions);
  const selectedDisplay = selected ? modelSelectDisplay(selected) : null;

  useEffect(() => {
    if (!open) return;
    searchRequestSeq.current += 1;
    const requestSeq = searchRequestSeq.current;
    if (!trimmedQuery) {
      setRemoteResults([]);
      setBusy(false);
      setError("");
      return;
    }
    let disposed = false;
    const timer = window.setTimeout(() => {
      setBusy(true);
      setError("");
      settingsApiResources.searchModels({ query: trimmedQuery, max_results: 30 })
        .then((result) => {
          if (disposed || requestSeq !== searchRequestSeq.current) return;
          setRemoteResults(result.models ?? []);
        })
        .catch((searchError: unknown) => {
          if (disposed || requestSeq !== searchRequestSeq.current) return;
          setRemoteResults([]);
          setError(searchError instanceof Error ? searchError.message : "モデル検索に失敗しました");
        })
        .finally(() => {
          if (!disposed && requestSeq === searchRequestSeq.current) setBusy(false);
        });
    }, 160);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [open, trimmedQuery]);

  const visibleOptions = useMemo(() => (
    buildVisibleModelOptions({
      options,
      selected,
      remoteOptions,
      query: trimmedQuery,
    })
  ), [options, remoteOptions, selected, trimmedQuery]);

  return (
    <div className="relative" data-settings-renderer="model_select">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-left text-sm text-zinc-200 outline-none transition-colors hover:border-zinc-700 focus:border-emerald-500/70"
      >
        <span className="min-w-0">
          <span className="block truncate">{selectedDisplay?.label || value || "モデルを選択"}</span>
          {selectedDisplay?.subtitle && (
            <span className="block truncate text-[11px] text-zinc-500">{selectedDisplay.subtitle}</span>
          )}
        </span>
        <ChevronDown size={14} className={cn("shrink-0 text-zinc-500 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <>
          <button type="button" aria-label="モデル検索を閉じる" className="fixed inset-0 rumi-layer-panel cursor-default" onClick={() => setOpen(false)} />
          <div className="absolute left-0 right-0 top-[calc(100%+6px)] rumi-layer-local-popover overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950 shadow-2xl">
            <label className="m-2 flex h-9 items-center gap-2 rounded-lg border border-zinc-800 bg-black/30 px-3 text-xs text-zinc-500 focus-within:border-zinc-600 focus-within:text-zinc-300">
              <Search size={14} />
              <input
                autoFocus
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={placeholder}
                className="min-w-0 flex-1 bg-transparent text-zinc-200 outline-none placeholder:text-zinc-600"
              />
              {busy && <Loader2 size={13} className="animate-spin text-zinc-500" />}
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="rounded p-0.5 text-zinc-600 hover:bg-zinc-800 hover:text-zinc-300"
                  aria-label="モデル検索をクリア"
                >
                  <X size={13} />
                </button>
              )}
            </label>
            {error && <div className="border-t border-zinc-800 px-3 py-2 text-[11px] text-rose-300">{error}</div>}
            <div className="max-h-72 overflow-y-auto border-t border-zinc-800 p-1">
              {visibleOptions.length > 0 ? visibleOptions.map((option) => {
                const active = option.value === value || option.qualified_model_id === value;
                const display = modelSelectDisplay(option);
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => {
                      onChange(option.value);
                      setOpen(false);
                    }}
                    className={cn(
                      "flex w-full items-start justify-between gap-3 rounded-md px-2.5 py-2 text-left transition-colors",
                      active ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
                    )}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-zinc-100">{display.label}</span>
                      <span className="block truncate text-[11px] text-zinc-500">{display.subtitle}</span>
                    </span>
                    <span className="flex max-w-[160px] flex-wrap justify-end gap-1">
                      {display.badges.map((badge) => (
                        <span key={badge.id} className="rounded-full border border-zinc-700 px-1.5 py-0.5 text-[10px] text-zinc-400">
                          {badge.label}
                        </span>
                      ))}
                      {active && <Check size={13} className="mt-1 shrink-0 text-emerald-300" />}
                    </span>
                  </button>
                );
              }) : (
                <div className="px-3 py-5 text-xs text-zinc-600">一致するモデルがありません。</div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function BuiltinModelSelectRenderer({ sectionId, field, value, sectionValues, onChange }: SettingsFieldRendererProps) {
  const targetFieldId = modelSelectTargetFieldId(field);
  const selectedValue = String(sectionValues?.[targetFieldId] ?? value ?? field.default ?? "");
  return (
    <SettingsFieldShell field={field}>
      <SettingsModelSearchField
        value={selectedValue}
        options={fieldOptions(field).map(modelFieldOptionToModelSelectOption)}
        onChange={(nextValue) => onChange(sectionId, targetFieldId, nextValue)}
      />
    </SettingsFieldShell>
  );
}
