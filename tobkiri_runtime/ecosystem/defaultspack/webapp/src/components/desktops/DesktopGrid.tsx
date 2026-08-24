import { Monitor } from "lucide-react";

import { cn } from "../../lib/cn";
import type { DesktopInputAction, DesktopInstance } from "../../features/sandboxes/types";
import type { DesktopDensity } from "./DesktopToolbar";
import { DesktopTile } from "./DesktopTile";

type DesktopGridProps = {
  desktops: DesktopInstance[];
  loading?: boolean;
  selectedSeatId: string | null;
  density: DesktopDensity;
  leaseSeatId: string | null;
  emptyReason?: "backend" | "filter" | "error";
  accessKeys?: Record<string, string>;
  controlBusy?: boolean;
  onSelect: (seatId: string) => void;
  onTakeOver: (seatId: string) => void;
  onReturnToAI: () => void;
  onInput: (seatId: string, input: DesktopInputAction) => void;
  onStart: (seatId: string) => void;
  onRestart: (seatId: string) => void;
  onStop: (seatId: string) => void;
  onDelete: (seatId: string) => void;
};

function DesktopSkeleton() {
  return (
    <div className="min-h-[280px] animate-pulse rounded-lg border border-zinc-800/70 bg-[#0a0a0c] p-3">
      <div className="flex items-center gap-2">
        <div className="h-8 w-8 rounded-md bg-zinc-900" />
        <div className="grid flex-1 gap-2">
          <div className="h-3 w-2/5 rounded bg-zinc-900" />
          <div className="h-2 w-1/4 rounded bg-zinc-900" />
        </div>
      </div>
      <div className="mt-3 h-40 rounded-md bg-black" />
      <div className="mt-3 h-8 rounded-md bg-zinc-900" />
    </div>
  );
}

export function DesktopGrid({
  desktops,
  loading = false,
  selectedSeatId,
  density,
  leaseSeatId,
  emptyReason = "backend",
  accessKeys = {},
  controlBusy = false,
  onSelect,
  onTakeOver,
  onReturnToAI,
  onInput,
  onStart,
  onRestart,
  onStop,
  onDelete,
}: DesktopGridProps) {
  const singleDesktop = desktops.length === 1;

  if (loading && desktops.length === 0) {
    return (
      <div
        className="grid grid-cols-1 gap-3 min-[900px]:grid-cols-2 min-[1400px]:grid-cols-3"
        role="status"
        aria-live="polite"
        aria-busy="true"
        aria-label="Loading desktop seats"
      >
        <div aria-hidden="true"><DesktopSkeleton /></div>
        <div aria-hidden="true"><DesktopSkeleton /></div>
        <div aria-hidden="true"><DesktopSkeleton /></div>
      </div>
    );
  }

  if (desktops.length === 0) {
    return (
      <div className="flex min-h-[360px] items-center justify-center rounded-lg border border-zinc-800/70 bg-[#0a0a0c]">
        <div className="max-w-sm px-5 text-center">
          <Monitor size={28} className="mx-auto text-zinc-600" />
          <p className="mt-3 text-sm font-semibold text-zinc-200">
            {emptyReason === "filter"
              ? "No matching desktop seats"
              : emptyReason === "error"
                ? "Desktop seats could not be refreshed"
                : "No desktop seats"}
          </p>
          <p className="mt-1 text-xs text-zinc-500">
            {emptyReason === "filter"
              ? "Desktop seats exist outside the current filter."
              : emptyReason === "error"
                ? "Retry to confirm the latest desktop seat state."
                : "The backend returned an empty desktop list."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn(
      "grid w-full grid-cols-1 items-start gap-3",
      !singleDesktop && "min-[900px]:grid-cols-2",
      !singleDesktop && (density === "dense" ? "min-[1400px]:grid-cols-4" : "min-[1400px]:grid-cols-3"),
    )}>
      {desktops.map((desktop) => (
        <DesktopTile
          key={desktop.seat_id}
          desktop={desktop}
          selected={desktop.seat_id === selectedSeatId}
          dense={density === "dense"}
          prominent={singleDesktop}
          hasLease={desktop.seat_id === leaseSeatId}
          accessKey={accessKeys[desktop.seat_id] || null}
          controlBusy={controlBusy && desktop.seat_id === selectedSeatId}
          onSelect={onSelect}
          onTakeOver={() => onTakeOver(desktop.seat_id)}
          onReturnToAI={onReturnToAI}
          onInput={(input) => onInput(desktop.seat_id, input)}
          onStart={() => onStart(desktop.seat_id)}
          onRestart={() => onRestart(desktop.seat_id)}
          onStop={() => onStop(desktop.seat_id)}
          onDelete={() => onDelete(desktop.seat_id)}
        />
      ))}
    </div>
  );
}
