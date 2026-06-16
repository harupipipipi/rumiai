import { Check, ChevronDown, RefreshCw, Search, Settings } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { KanbanBoard, KanbanBoardScope, KanbanBoardScopeType } from "../../lib/api";
import { cn } from "../../lib/cn";

export type KanbanScopeOption = {
  scope: KanbanBoardScope;
  label: string;
  description: string;
  disabled?: boolean;
};

function scopeKey(scope: KanbanBoardScope): string {
  return `${scope.type}:${scope.id}`;
}

function scopeChipLabel(type: KanbanBoardScopeType): string {
  if (type === "conversation") return "chat";
  if (type === "workspace") return "workspace";
  if (type === "company") return "company";
  if (type === "group") return "group";
  return "runs";
}

export function filterKanbanScopeOptions(scopeOptions: KanbanScopeOption[], query: string): KanbanScopeOption[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return scopeOptions;
  return scopeOptions.filter((option) => [
    option.label,
    option.description,
    option.scope.type,
    option.scope.id,
  ].join(" ").toLowerCase().includes(normalized));
}

function BoardScopeSelector({
  scope,
  scopeOptions,
  onScopeChange,
}: {
  scope: KanbanBoardScope;
  scopeOptions: KanbanScopeOption[];
  onScopeChange: (scope: KanbanBoardScope) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const activeScopeKey = scopeKey(scope);
  const activeOption = scopeOptions.find((option) => scopeKey(option.scope) === activeScopeKey);
  const filteredOptions = useMemo(() => filterKanbanScopeOptions(scopeOptions, query), [query, scopeOptions]);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const focusTimer = window.setTimeout(() => searchRef.current?.focus(), 0);
    return () => window.clearTimeout(focusTimer);
  }, [open]);

  const chooseScope = (option: KanbanScopeOption) => {
    if (option.disabled) return;
    onScopeChange(option.scope);
    setOpen(false);
    setQuery("");
  };

  return (
    <div ref={rootRef} className="relative min-w-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex h-9 w-full min-w-0 items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950 px-2.5 text-left text-zinc-200 transition hover:border-zinc-700 hover:bg-zinc-900/80 focus:border-zinc-600 focus:outline-none"
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[12px] font-medium">{activeOption?.label || "Select board"}</span>
          <span className="mt-0.5 block truncate text-[9px] text-zinc-600">{activeOption?.description || scope.id}</span>
        </span>
        <ChevronDown size={14} className={cn("shrink-0 text-zinc-500 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute left-0 top-full rumi-layer-modal mt-1.5 w-[min(360px,calc(100vw-32px))] overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 shadow-2xl shadow-black/50">
          <div className="border-b border-zinc-800/70 p-2">
            <div className="relative">
              <Search size={12} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-600" />
              <input
                ref={searchRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search boards"
                className="h-8 w-full rounded-md border border-zinc-800 bg-[#09090b] pl-8 pr-2 text-[12px] text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
              />
            </div>
          </div>
          <div role="listbox" aria-label="Kanban board selector" className="max-h-72 overflow-y-auto p-1.5">
            {filteredOptions.map((option) => {
              const active = scopeKey(option.scope) === activeScopeKey;
              return (
                <button
                  key={scopeKey(option.scope)}
                  type="button"
                  role="option"
                  aria-selected={active}
                  disabled={option.disabled}
                  onClick={() => chooseScope(option)}
                  className={cn(
                    "flex w-full min-w-0 items-center gap-2 rounded-md px-2.5 py-2 text-left transition",
                    active
                      ? "bg-zinc-800/90 text-zinc-100"
                      : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100",
                    option.disabled && "cursor-not-allowed opacity-40",
                  )}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12px] font-medium">{option.label}</span>
                    <span className="mt-0.5 block truncate text-[10px] text-zinc-600">{option.description}</span>
                  </span>
                  {active && <Check size={13} className="shrink-0 text-emerald-300" />}
                </button>
              );
            })}
            {filteredOptions.length === 0 && (
              <div className="px-3 py-6 text-center text-[11px] text-zinc-600">No boards found.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function KanbanToolbar({
  board,
  scope,
  scopeOptions,
  loading,
  backendAvailable,
  search,
  onSearchChange,
  onScopeChange,
  onCreateCard,
  onReload,
  onOpenSettings,
}: {
  board: KanbanBoard | null;
  scope: KanbanBoardScope;
  scopeOptions: KanbanScopeOption[];
  loading: boolean;
  backendAvailable: boolean;
  search: string;
  onSearchChange: (value: string) => void;
  onScopeChange: (scope: KanbanBoardScope) => void;
  onCreateCard: () => void;
  onReload: () => void;
  onOpenSettings: () => void;
}) {
  return (
    <div className="shrink-0 border-b border-zinc-800/70 bg-[#09090b]/95 px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="truncate text-[15px] font-semibold text-zinc-100">{board?.title || "Kanban"}</h2>
            <span className="rounded-full border border-zinc-800 bg-zinc-950 px-2 py-0.5 text-[10px] text-zinc-500">
              {scopeChipLabel(scope.type)}
            </span>
            <span className={cn(
              "rounded-full border px-2 py-0.5 text-[10px]",
              backendAvailable ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-200" : "border-amber-500/25 bg-amber-500/10 text-amber-200",
            )}>
              {backendAvailable ? "persisted" : "local draft"}
            </span>
          </div>
          <p className="mt-1 truncate text-[11px] text-zinc-600">{scope.id}</p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onCreateCard}
            className="h-8 rounded-md bg-zinc-100 px-3 text-[12px] font-semibold text-zinc-950 transition hover:bg-white"
          >
            New card
          </button>
          <button
            type="button"
            onClick={onReload}
            disabled={loading}
            className="flex h-8 w-8 items-center justify-center rounded-md border border-zinc-800 text-zinc-500 transition hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40"
            title="Reload"
            aria-label="Reload"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
          <button
            type="button"
            onClick={onOpenSettings}
            className="flex h-8 w-8 items-center justify-center rounded-md border border-zinc-800 text-zinc-500 transition hover:bg-zinc-800 hover:text-zinc-100"
            title="Settings"
            aria-label="Settings"
          >
            <Settings size={13} />
          </button>
        </div>
      </div>

      <div className="mt-2 grid min-w-0 grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] gap-2 max-[700px]:grid-cols-1">
        <BoardScopeSelector
          scope={scope}
          scopeOptions={scopeOptions}
          onScopeChange={onScopeChange}
        />
        <div className="relative min-w-0">
          <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-600" />
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search cards"
            aria-label="Search cards"
            className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 pl-8 pr-2 text-[12px] text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
          />
        </div>
      </div>
    </div>
  );
}
