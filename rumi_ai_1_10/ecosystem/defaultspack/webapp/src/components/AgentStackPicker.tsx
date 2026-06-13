import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, FolderCog, PanelRightOpen, Plus, RotateCcw, Settings2, Sparkles, X } from "lucide-react";

import type { ChatHeaderAgentStackControls } from "../renderers/types";

type AgentStackPickerProps = {
  controls: ChatHeaderAgentStackControls;
  canOpenSettings: boolean;
  canShowPreview: boolean;
  showPreview: boolean;
  onOpenSettings: () => void;
  onTogglePreview: () => void;
};

function chipClassName(available: boolean): string {
  return available
    ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-100 hover:border-cyan-400/50 hover:bg-cyan-500/15"
    : "border-amber-500/30 bg-amber-500/10 text-amber-100 hover:border-amber-400/50 hover:bg-amber-500/15";
}

function optionClassName(selected: boolean, available: boolean): string {
  if (selected && available) {
    return "border-cyan-500/30 bg-cyan-500/10 text-cyan-50";
  }
  if (selected && !available) {
    return "border-amber-500/30 bg-amber-500/10 text-amber-100";
  }
  return "border-zinc-800 bg-zinc-950/60 text-zinc-200 hover:border-zinc-700 hover:bg-zinc-900";
}

export function AgentStackPicker({
  controls,
  canOpenSettings,
  canShowPreview,
  showPreview,
  onOpenSettings,
  onTogglePreview,
}: AgentStackPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const filteredOptions = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase();
    if (!needle) return controls.options;
    return controls.options.filter((option) => {
      const haystack = [option.id, option.label, option.description ?? "", option.note ?? ""].join(" ").toLowerCase();
      return haystack.includes(needle);
    });
  }, [controls.options, deferredQuery]);

  useEffect(() => {
    if (!open) return undefined;
    const handlePointerDown = (event: PointerEvent) => {
      if (!(event.target instanceof Node)) return;
      if (popoverRef.current?.contains(event.target)) return;
      setOpen(false);
    };
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  return (
    <div className="relative flex items-center gap-2" ref={popoverRef}>
      {canShowPreview && (
        <button
          type="button"
          title={showPreview ? "Hide canvas" : "Show canvas"}
          onClick={onTogglePreview}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-950/70 text-zinc-400 transition-colors hover:border-zinc-700 hover:text-zinc-100"
        >
          <PanelRightOpen size={14} />
        </button>
      )}
      {canOpenSettings && (
        <button
          type="button"
          title="Settings"
          onClick={onOpenSettings}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-950/70 text-zinc-400 transition-colors hover:border-zinc-700 hover:text-zinc-100"
        >
          <Settings2 size={14} />
        </button>
      )}
      <span className="hidden rounded-full border border-zinc-800 bg-zinc-950/70 px-2 py-1 text-[10px] font-medium tracking-[0.18em] text-zinc-500 uppercase min-[860px]:inline-flex">
        {controls.sourceLabel}
      </span>
      <button
        type="button"
        title={`Add ${controls.featureName}`}
        onClick={() => setOpen((current) => !current)}
        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-950/70 text-zinc-300 transition-colors hover:border-cyan-500/40 hover:bg-cyan-500/10 hover:text-cyan-100"
      >
        <Plus size={15} />
      </button>
      <div className="flex max-w-[420px] flex-wrap items-center justify-end gap-1.5">
        {controls.chips.length === 0 ? (
          <span className="inline-flex h-8 items-center rounded-full border border-zinc-800 bg-zinc-950/70 px-3 text-xs text-zinc-500">
            {controls.sourceLabel}
          </span>
        ) : (
          controls.chips.map((chip) => (
            <button
              key={chip.id}
              type="button"
              title={chip.note ? `${chip.label} · ${chip.note}` : chip.label}
              onClick={() => controls.onRemoveProfile(chip.id)}
              className={`inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs transition-colors ${chipClassName(chip.available)}`}
            >
              {!chip.available && <AlertTriangle size={12} />}
              <span className="max-w-[150px] truncate">{chip.label}</span>
              <X size={12} />
            </button>
          ))
        )}
      </div>

      {open && (
        <div className="absolute right-0 top-[calc(100%+8px)] rumi-layer-local-popover w-[min(420px,calc(100vw-32px))] rounded-2xl border border-zinc-800 bg-zinc-950/98 p-3 shadow-2xl backdrop-blur-md">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Sparkles size={14} className="shrink-0 text-cyan-300" />
                <p className="text-sm font-semibold text-zinc-100">{controls.featureName}</p>
              </div>
              <p className="mt-1 text-xs text-zinc-500">{controls.sourceLabel}</p>
            </div>
            {controls.parseError && (
              <div className="max-w-[180px] rounded-xl border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-100">
                JSON fallback active
              </div>
            )}
          </div>

          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search profiles, tools, skills, model rules"
            className="mb-3 w-full rounded-xl border border-zinc-800 bg-zinc-900/90 px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
          />

          <div className="max-h-[300px] space-y-2 overflow-auto pr-1">
            {filteredOptions.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => {
                  if (option.selected) {
                    controls.onRemoveProfile(option.id);
                  } else {
                    controls.onAddProfile(option.id);
                  }
                }}
                className={`w-full rounded-2xl border px-3 py-2 text-left transition-colors ${optionClassName(option.selected, option.available)}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium">{option.label}</span>
                      {option.selected && (
                        <span className="rounded-full border border-white/10 bg-white/10 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.18em]">
                          active
                        </span>
                      )}
                    </div>
                    {option.description && (
                      <p className="mt-1 text-xs text-zinc-400">{option.description}</p>
                    )}
                    {option.note && (
                      <p className="mt-1 text-[11px] text-amber-200">{option.note}</p>
                    )}
                  </div>
                  <span className="shrink-0 text-[11px] text-zinc-500">{option.selected ? "Remove" : "Add"}</span>
                </div>
              </button>
            ))}
            {filteredOptions.length === 0 && (
              <div className="rounded-2xl border border-dashed border-zinc-800 px-3 py-6 text-center text-sm text-zinc-500">
                No profiles matched.
              </div>
            )}
          </div>

          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <button
              type="button"
              onClick={controls.onSetDefault}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-xs text-zinc-200 transition-colors hover:border-zinc-700 hover:bg-zinc-900"
            >
              <Sparkles size={13} />
              Set Default
            </button>
            <button
              type="button"
              disabled={!controls.canSetGroupDefault}
              onClick={controls.onSetGroupDefault}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-xs text-zinc-200 transition-colors enabled:hover:border-zinc-700 enabled:hover:bg-zinc-900 disabled:cursor-not-allowed disabled:text-zinc-600"
            >
              <FolderCog size={13} />
              Group Default
            </button>
            <button
              type="button"
              onClick={controls.onResetToDefault}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-zinc-800 bg-zinc-900/80 px-3 py-2 text-xs text-zinc-200 transition-colors hover:border-zinc-700 hover:bg-zinc-900"
            >
              <RotateCcw size={13} />
              Reset
            </button>
          </div>

          {controls.parseError && (
            <div className="mt-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              Profile JSON could not be parsed, so the built-in `coding`, `subagent`, `all`, `yolo` profiles are being used instead.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
