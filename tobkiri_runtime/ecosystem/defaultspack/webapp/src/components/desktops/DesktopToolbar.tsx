import { Grid2X2, Grid3X3, Plus, RefreshCw, SlidersHorizontal } from "lucide-react";

import { cn } from "../../lib/cn";

export type DesktopFilter = "all" | "running";
export type DesktopDensity = "comfortable" | "dense";

type DesktopToolbarProps = {
  totalCount: number;
  runningCount: number;
  loading?: boolean;
  filter: DesktopFilter;
  density: DesktopDensity;
  doctorLoading?: boolean;
  canCreate: boolean;
  onFilterChange: (filter: DesktopFilter) => void;
  onDensityChange: (density: DesktopDensity) => void;
  onCreate: () => void;
  onDoctor: () => void;
};

function segmentedButtonClassName(active: boolean) {
  return cn(
    "h-7 rounded-md px-2 text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500/70",
    active ? "bg-zinc-100 text-zinc-950" : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100",
  );
}

export function DesktopToolbar({
  totalCount,
  runningCount,
  loading = false,
  filter,
  density,
  doctorLoading = false,
  canCreate,
  onFilterChange,
  onDensityChange,
  onCreate,
  onDoctor,
}: DesktopToolbarProps) {
  const isInitialRefresh = loading && totalCount === 0;
  const runningLabel = isInitialRefresh ? "Refreshing" : `${runningCount} running`;
  const seatsLabel = isInitialRefresh
    ? "Loading seats..."
    : `${totalCount} seats · ${loading ? "Refreshing snapshots" : "Live snapshots"}`;

  return (
    <div className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-zinc-800/70 bg-[#09090b] px-4 py-3">
      <div
        className="min-w-0"
        role="status"
        aria-live="polite"
        aria-busy={isInitialRefresh}
      >
        <div className="flex items-center gap-2">
          <h1 className="truncate text-[15px] font-semibold text-zinc-100">Desktops</h1>
          <span className="rounded-md border border-emerald-500/20 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-200">
            {runningLabel}
          </span>
        </div>
        <p className="mt-0.5 truncate text-[11px] text-zinc-500">{seatsLabel}</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950/70 p-0.5" aria-label="Desktop filter">
          <button type="button" onClick={() => onFilterChange("all")} className={segmentedButtonClassName(filter === "all")}>
            All
          </button>
          <button type="button" onClick={() => onFilterChange("running")} className={segmentedButtonClassName(filter === "running")}>
            Running
          </button>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950/70 p-0.5" aria-label="Desktop density">
          <button
            type="button"
            onClick={() => onDensityChange("comfortable")}
            className={segmentedButtonClassName(density === "comfortable")}
            title="2 x 2 density"
            aria-label="Comfortable grid"
          >
            <Grid2X2 size={13} />
          </button>
          <button
            type="button"
            onClick={() => onDensityChange("dense")}
            className={segmentedButtonClassName(density === "dense")}
            title="High-density grid"
            aria-label="Dense grid"
          >
            <Grid3X3 size={13} />
          </button>
        </div>
        <button
          type="button"
          onClick={onDoctor}
          disabled={doctorLoading}
          className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-950/70 px-2 text-[11px] font-medium text-zinc-300 transition-colors hover:border-zinc-700 hover:bg-zinc-900 hover:text-zinc-100 disabled:cursor-wait disabled:opacity-55"
        >
          {doctorLoading ? <SlidersHorizontal size={13} /> : <RefreshCw size={13} />}
          <span>Run doctor again</span>
        </button>
        <button
          type="button"
          onClick={onCreate}
          disabled={!canCreate}
          className="flex h-8 items-center gap-1.5 rounded-md bg-zinc-100 px-3 text-[11px] font-semibold text-zinc-950 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus size={13} />
          <span>New Desktop</span>
        </button>
      </div>
    </div>
  );
}
