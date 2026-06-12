import { RefreshCw, Search, Settings } from "lucide-react";

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
  const activeScopeKey = scopeKey(scope);

  return (
    <div className="shrink-0 border-b border-zinc-800/70 bg-[#09090b]/95 px-3 py-3">
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

        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <div className="relative min-w-[180px] flex-1 sm:flex-none">
            <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-600" />
            <input
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Search cards, chats, groups"
              className="h-8 w-full rounded-md border border-zinc-800 bg-zinc-950 pl-8 pr-2 text-[12px] text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
            />
          </div>
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

      <div className="mt-3 flex gap-1.5 overflow-x-auto">
        {scopeOptions.map((option) => {
          const active = scopeKey(option.scope) === activeScopeKey;
          return (
            <button
              key={scopeKey(option.scope)}
              type="button"
              disabled={option.disabled}
              onClick={() => onScopeChange(option.scope)}
              className={cn(
                "min-w-28 rounded-md border px-2.5 py-1.5 text-left transition",
                active
                  ? "border-zinc-600 bg-zinc-800/80 text-zinc-100"
                  : "border-zinc-800 bg-zinc-950/55 text-zinc-500 hover:border-zinc-700 hover:text-zinc-200",
                option.disabled && "cursor-not-allowed opacity-40",
              )}
            >
              <span className="block truncate text-[11px] font-medium">{option.label}</span>
              <span className="mt-0.5 block truncate text-[9px] text-zinc-600">{option.description}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
