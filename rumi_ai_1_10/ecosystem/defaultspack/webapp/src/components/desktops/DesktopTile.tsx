import { AlertTriangle, Bot, Circle, Monitor, UserCheck } from "lucide-react";
import { useRef } from "react";

import { cn } from "../../lib/cn";
import type { DesktopInstance } from "../../features/sandboxes/types";
import { useDesktopFrame } from "../../features/sandboxes/useDesktopFrames";
import { pointerToDesktopCoordinates } from "./desktopCoordinates";
import { DesktopControlSurface } from "./DesktopControlSurface";

type DesktopTileProps = {
  desktop: DesktopInstance;
  selected: boolean;
  dense?: boolean;
  hasLease: boolean;
  accessKey?: string | null;
  controlBusy?: boolean;
  onSelect: (seatId: string) => void;
  onTakeOver: () => void;
  onReturnToAI: () => void;
  onInputClick: (x: number, y: number) => void;
  onStart: () => void;
  onRestart: () => void;
  onStop: () => void;
  onDelete: () => void;
};

function statusTone(status: string): string {
  if (status === "running") return "text-emerald-300";
  if (status === "provisioning" || status === "starting" || status === "creating") return "text-amber-300";
  if (status === "failed") return "text-red-300";
  return "text-zinc-500";
}

function frameAgeLabel(ageMs: number | null): string {
  if (ageMs === null) return "No frame";
  if (ageMs < 1000) return "now";
  if (ageMs < 60000) return `${Math.round(ageMs / 1000)}s ago`;
  return `${Math.round(ageMs / 60000)}m ago`;
}

export function DesktopTile({
  desktop,
  selected,
  dense = false,
  hasLease,
  accessKey,
  controlBusy = false,
  onSelect,
  onTakeOver,
  onReturnToAI,
  onInputClick,
  onStart,
  onRestart,
  onStop,
  onDelete,
}: DesktopTileProps) {
  const frameRegionRef = useRef<HTMLDivElement | null>(null);
  const { frame, error, ageMs, pollNow } = useDesktopFrame({
    seatId: desktop.seat_id,
    status: desktop.status,
    selected,
    hasControlLease: hasLease,
    accessKey,
  });
  const resolution = frame
    ? { width: frame.width, height: frame.height }
    : desktop.resolution ?? { width: 1280, height: 800 };
  const frameAspectRatio = `${Math.max(resolution.width, 1)} / ${Math.max(resolution.height, 1)}`;
  const provider = desktop.provider_label || desktop.provider_id || "provider pending";
  const controlLabel = hasLease
    ? "Human control"
    : desktop.control?.holder === "ai"
      ? "AI control"
      : "Control available";

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!hasLease || !frame || !frameRegionRef.current) return;
    const rect = frameRegionRef.current.getBoundingClientRect();
    const mapped = pointerToDesktopCoordinates(
      { x: event.clientX - rect.left, y: event.clientY - rect.top },
      { width: rect.width, height: rect.height },
      { width: resolution.width, height: resolution.height },
    );
    if (!mapped) return;
    event.preventDefault();
    onInputClick(mapped.desktopX, mapped.desktopY);
  };

  return (
    <article
      className={cn(
        "group flex min-h-[280px] flex-col rounded-lg border bg-[#0a0a0c] transition-colors",
        selected ? "border-zinc-500 text-zinc-100" : "border-zinc-800/70 text-zinc-300 hover:border-zinc-700",
        dense && "min-h-[238px]",
      )}
      data-testid={`desktop-tile-${desktop.seat_id}`}
    >
      <button
        type="button"
        onClick={() => onSelect(desktop.seat_id)}
        aria-current={selected ? "page" : undefined}
        className="flex min-h-12 items-center justify-between gap-2 border-b border-zinc-800/70 px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500/70"
      >
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-zinc-800 bg-zinc-950 text-zinc-300">
            <Monitor size={15} />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{desktop.name}</p>
            <p className="truncate text-[11px] text-zinc-500">{provider}</p>
          </div>
        </div>
        <span className={cn("flex shrink-0 items-center gap-1 text-[11px] font-medium", statusTone(desktop.status))}>
          <Circle size={9} fill="currentColor" />
          {desktop.status}
        </span>
      </button>

      <div
        ref={frameRegionRef}
        onPointerDown={handlePointerDown}
        className={cn(
          "relative m-3 flex min-h-[154px] items-center justify-center overflow-hidden rounded-md border border-zinc-800 bg-black",
          hasLease ? "cursor-crosshair" : "cursor-default",
          dense && "min-h-[128px]",
        )}
        style={{ aspectRatio: frameAspectRatio }}
        role="img"
        aria-label={`${desktop.name} live snapshot`}
      >
        {frame ? (
          <img src={frame.object_url} alt="" className="h-full w-full object-contain" draggable={false} />
        ) : (
          <div className="flex flex-col items-center gap-2 text-zinc-600">
            {desktop.status === "failed" ? <AlertTriangle size={24} /> : <Monitor size={24} />}
            <span className="text-xs">{desktop.status === "running" ? "Waiting for first snapshot" : desktop.status}</span>
          </div>
        )}
        {error && (
          <div className="absolute inset-x-2 bottom-2 rounded-md border border-red-500/25 bg-red-950/80 px-2 py-1 text-[11px] text-red-100">
            {error}
          </div>
        )}
      </div>

      <div className="grid gap-2 px-3 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-500">
          <span className="flex items-center gap-1">
            {hasLease ? <UserCheck size={12} className="text-zinc-300" /> : <Bot size={12} />}
            {controlLabel}
          </span>
          <span>Last frame {frameAgeLabel(ageMs ?? desktop.frame?.age_ms ?? null)}</span>
        </div>
        <DesktopControlSurface
          desktop={desktop}
          hasLease={hasLease}
          busy={controlBusy}
          onTakeOver={onTakeOver}
          onReturnToAI={onReturnToAI}
          onSnapshot={() => void pollNow()}
          onStart={onStart}
          onRestart={onRestart}
          onStop={onStop}
          onDelete={onDelete}
        />
      </div>
    </article>
  );
}
