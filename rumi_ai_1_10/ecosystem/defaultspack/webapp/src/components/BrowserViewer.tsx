import { useMemo, useState } from "react";
import { Camera, Circle, Globe2, Hand, Play, RefreshCw, RotateCw, ScrollText } from "lucide-react";

import type { BrowserActionLogEntry, BrowserTab, BrowserViewerState } from "../lib/api";
import { cn } from "../lib/cn";

export function activeBrowserTab(state: BrowserViewerState): BrowserTab | null {
  if (state.active_tab_id) {
    const explicit = state.tabs.find((tab) => tab.id === state.active_tab_id);
    if (explicit) return explicit;
  }
  return state.tabs.find((tab) => tab.active) ?? state.tabs[0] ?? null;
}

export function browserViewerSnapshotRefs(state: BrowserViewerState): string[] {
  return [
    state.snapshot_ref,
    ...state.tabs.map((tab) => tab.snapshot_ref),
  ].filter((value, index, all): value is string => Boolean(value) && all.indexOf(value) === index);
}

function logTime(entry: BrowserActionLogEntry): string {
  if (!entry.timestamp) return "";
  const time = typeof entry.timestamp === "number" ? entry.timestamp : Date.parse(String(entry.timestamp));
  if (!Number.isFinite(time)) return String(entry.timestamp);
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(time);
}

export function BrowserViewer({
  state,
  loading = false,
  onRefresh,
  onManualTakeover,
  onResume,
  onAction,
}: {
  state: BrowserViewerState;
  loading?: boolean;
  onRefresh?: () => void;
  onManualTakeover?: () => void;
  onResume?: () => void;
  onAction?: (action: "screenshot" | "snapshot" | "resume", payload?: Record<string, unknown>) => void;
}) {
  const initialTab = activeBrowserTab(state)?.id ?? "";
  const [selectedTabId, setSelectedTabId] = useState(initialTab);
  const selectedTab = useMemo(
    () => state.tabs.find((tab) => tab.id === selectedTabId) ?? activeBrowserTab(state),
    [selectedTabId, state],
  );
  const screenshotUrl = selectedTab?.screenshot_url || state.screenshot_url;
  const snapshotRefs = useMemo(() => browserViewerSnapshotRefs(state), [state]);
  const manual = state.manual_takeover === true;

  return (
    <section className="flex h-full min-h-0 flex-col bg-[#09090b] text-zinc-100">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">Browser Viewer</h2>
          <p className="mt-0.5 truncate text-[11px] text-zinc-500">
            profile {state.profile_id || "default"} · {manual ? `manual ${state.takeover_owner || ""}` : "agent control"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={loading}
              className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
              title="Refresh browser viewer"
            >
              <RefreshCw size={14} /> Refresh
            </button>
          )}
          <button
            type="button"
            onClick={() => (manual ? (onResume?.(), onAction?.("resume")) : onManualTakeover?.())}
            className={cn(
              "flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-semibold",
              manual ? "bg-zinc-100 text-zinc-950 hover:bg-white" : "border border-zinc-800 bg-zinc-900 text-zinc-300 hover:bg-zinc-800",
            )}
            title={manual ? "Resume agent control" : "Manual takeover"}
          >
            {manual ? <Play size={14} /> : <Hand size={14} />}
            {manual ? "Resume" : "Takeover"}
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:grid lg:grid-cols-[1fr_280px]">
        <main className="flex min-h-0 flex-col">
          <div className="flex max-w-full gap-1 overflow-x-auto border-b border-zinc-800 px-3 py-2">
            {state.tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setSelectedTabId(tab.id)}
                className={cn(
                  "flex h-8 max-w-[220px] flex-shrink-0 items-center gap-2 rounded-md border px-2 text-xs transition-colors",
                  selectedTab?.id === tab.id
                    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
                    : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200",
                )}
                title={tab.url || tab.title || tab.id}
              >
                <Circle size={8} className={tab.active ? "fill-emerald-400 text-emerald-400" : "text-zinc-600"} />
                <span className="truncate">{tab.title || tab.url || tab.id}</span>
              </button>
            ))}
            {state.tabs.length === 0 && <div className="px-1 py-1 text-xs text-zinc-500">No tabs</div>}
          </div>

          <div className="grid gap-2 border-b border-zinc-800 p-3 sm:grid-cols-3">
            <button
              type="button"
              onClick={() => onAction?.("screenshot", { tab_id: selectedTab?.id })}
              className="flex h-8 items-center justify-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-xs text-zinc-300 hover:bg-zinc-800"
              title="Capture screenshot"
            >
              <Camera size={14} /> Screenshot
            </button>
            <button
              type="button"
              onClick={() => onAction?.("snapshot", { tab_id: selectedTab?.id })}
              className="flex h-8 items-center justify-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-xs text-zinc-300 hover:bg-zinc-800"
              title="Capture DOM snapshot"
            >
              <ScrollText size={14} /> Snapshot
            </button>
            <button
              type="button"
              onClick={() => onAction?.("resume", { tab_id: selectedTab?.id })}
              className="flex h-8 items-center justify-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-xs text-zinc-300 hover:bg-zinc-800"
              title="Resume automation"
            >
              <RotateCw size={14} /> Resume
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-auto bg-zinc-950">
            {screenshotUrl ? (
              <img src={screenshotUrl} alt="Browser screenshot" className="h-full min-h-[360px] w-full object-contain" />
            ) : (
              <div className="flex min-h-[360px] items-center justify-center text-sm text-zinc-600">
                No screenshot
              </div>
            )}
          </div>
        </main>

        <aside className="min-h-0 overflow-y-auto border-t border-zinc-800 lg:border-l lg:border-t-0">
          <section className="border-b border-zinc-800 p-3">
            <h3 className="text-xs font-semibold text-zinc-300">Active Tab</h3>
            <div className="mt-2 space-y-1 text-[11px] text-zinc-500">
              <div className="flex min-w-0 items-center gap-1.5">
                <Globe2 size={13} />
                <span className="truncate">{selectedTab?.url || "about:blank"}</span>
              </div>
              <div className="truncate">status {selectedTab?.status || "unknown"}</div>
              <div className="truncate">snapshot {selectedTab?.snapshot_ref || state.snapshot_ref || "none"}</div>
            </div>
          </section>

          <section className="border-b border-zinc-800 p-3">
            <h3 className="text-xs font-semibold text-zinc-300">Snapshots</h3>
            <div className="mt-2 flex flex-wrap gap-1">
              {snapshotRefs.map((ref) => (
                <span key={ref} className="max-w-full truncate rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 text-[10px] text-zinc-500">
                  {ref}
                </span>
              ))}
              {snapshotRefs.length === 0 && <span className="text-[11px] text-zinc-600">none</span>}
            </div>
          </section>

          <section className="p-3">
            <h3 className="text-xs font-semibold text-zinc-300">Action Log</h3>
            <div className="mt-2 space-y-2">
              {(state.action_log ?? []).slice(0, 20).map((entry) => (
                <div key={entry.id} className="min-w-0 border-l border-zinc-800 pl-2">
                  <div className="flex min-w-0 items-center justify-between gap-2">
                    <span className="truncate text-[11px] font-medium text-zinc-300">{entry.action}</span>
                    <span className="flex-shrink-0 text-[10px] text-zinc-600">{logTime(entry)}</span>
                  </div>
                  <div className="mt-0.5 truncate text-[10px] text-zinc-500">
                    {entry.status || "queued"} {entry.tool_name ? `· ${entry.tool_name}` : ""}
                  </div>
                  {entry.message && <div className="mt-0.5 line-clamp-2 text-[10px] text-zinc-600">{entry.message}</div>}
                </div>
              ))}
              {(state.action_log ?? []).length === 0 && <div className="text-[11px] text-zinc-600">No actions</div>}
            </div>
          </section>
        </aside>
      </div>
    </section>
  );
}
