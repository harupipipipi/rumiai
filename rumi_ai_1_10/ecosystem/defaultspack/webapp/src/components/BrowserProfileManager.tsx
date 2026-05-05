import { useMemo, useState, type FormEvent } from "react";
import { CheckCircle2, Cookie, Database, Globe2, Plus, RefreshCw, Star, Trash2 } from "lucide-react";

import { api, type BrowserProfile } from "../lib/api";
import { cn } from "../lib/cn";

export type BrowserProfileSummary = {
  id: string;
  label: string;
  active: boolean;
  storageLabel: string;
  cookiesLabel: string;
};

export function browserProfileKey(profile: BrowserProfile): string {
  return profile.profile_id || profile.id;
}

export function formatBytes(value?: number): string {
  const size = Number(value ?? 0);
  if (!Number.isFinite(size) || size <= 0) return "0 B";
  if (size >= 1024 * 1024 * 1024) return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${Math.round(size)} B`;
}

export function summarizeBrowserProfile(profile: BrowserProfile, activeProfileId?: string | null): BrowserProfileSummary {
  const id = browserProfileKey(profile);
  const storageBytes = Number(profile.storage_bytes ?? profile.cache_bytes ?? 0);
  return {
    id,
    label: profile.label || id,
    active: profile.active === true || id === activeProfileId,
    storageLabel: formatBytes(storageBytes),
    cookiesLabel: `${Number(profile.cookie_count ?? 0)} cookies`,
  };
}

export function BrowserProfileManager({
  profiles,
  activeProfileId,
  loading = false,
  onRefresh,
  onCreate,
  onSetActive,
  onDelete,
  onAction,
}: {
  profiles: BrowserProfile[];
  activeProfileId?: string | null;
  loading?: boolean;
  onRefresh?: () => void;
  onCreate?: (payload: { label: string; set_active?: boolean }) => Promise<void> | void;
  onSetActive?: (profile: BrowserProfile) => Promise<void> | void;
  onDelete?: (profile: BrowserProfile) => Promise<void> | void;
  onAction?: (profile: BrowserProfile, action: "clear_cache" | "clear_cookies") => Promise<void> | void;
}) {
  const [label, setLabel] = useState("");
  const [setActive, setSetActive] = useState(true);
  const [message, setMessage] = useState("");
  const [busyId, setBusyId] = useState("");
  const summaries = useMemo(
    () => profiles.map((profile) => ({ profile, summary: summarizeBrowserProfile(profile, activeProfileId) })),
    [activeProfileId, profiles],
  );

  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (!label.trim()) return;
    setMessage("");
    setBusyId("__new__");
    try {
      if (onCreate) {
        await onCreate({ label: label.trim(), set_active: setActive });
      } else {
        await api.createBrowserProfile({ label: label.trim(), set_active: setActive });
      }
      setLabel("");
      setMessage("Created");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Create failed");
    } finally {
      setBusyId("");
    }
  };

  const run = async (profile: BrowserProfile, action: "activate" | "delete" | "clear_cache" | "clear_cookies") => {
    const id = browserProfileKey(profile);
    setBusyId(id);
    setMessage("");
    try {
      if (action === "activate") {
        if (onSetActive) await onSetActive(profile);
        else await api.setActiveBrowserProfile(id);
      } else if (action === "delete") {
        if (onDelete) await onDelete(profile);
        else await api.deleteBrowserProfile(id);
      } else if (onAction) {
        await onAction(profile, action);
      } else {
        await api.browserProfileAction(id, action);
      }
      setMessage(action.replace("_", " "));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `${action} failed`);
    } finally {
      setBusyId("");
    }
  };

  return (
    <section className="flex h-full min-h-0 flex-col bg-[#09090b] text-zinc-100">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">Browser Profiles</h2>
          <p className="mt-0.5 truncate text-[11px] text-zinc-500">{summaries.length} profiles · active {activeProfileId || "default"}</p>
        </div>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
            title="Refresh browser profiles"
          >
            <RefreshCw size={14} /> Refresh
          </button>
        )}
      </header>

      <form onSubmit={create} className="grid gap-2 border-b border-zinc-800 p-4 md:grid-cols-[1fr_auto_auto]">
        <input
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Profile label"
          className="h-9 rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
        />
        <button
          type="button"
          onClick={() => setSetActive(!setActive)}
          aria-pressed={setActive}
          className={cn(
            "flex h-9 items-center justify-center gap-1.5 rounded-md border px-3 text-xs font-medium",
            setActive ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200" : "border-zinc-800 bg-zinc-900 text-zinc-400",
          )}
          title="Set active"
        >
          <Star size={14} /> Active
        </button>
        <button
          type="submit"
          disabled={!label.trim() || busyId === "__new__"}
          className="flex h-9 items-center justify-center gap-1.5 rounded-md bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white disabled:opacity-50"
          title="Create profile"
        >
          <Plus size={14} /> Create
        </button>
      </form>

      {message && <div className="border-b border-zinc-800 px-4 py-2 text-xs text-zinc-400">{message}</div>}

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="grid gap-2 lg:grid-cols-2">
          {summaries.map(({ profile, summary }) => {
            const busy = busyId === summary.id;
            return (
              <article key={summary.id} className="rounded-lg border border-zinc-800 bg-zinc-950/60">
                <div className="flex flex-wrap items-start justify-between gap-3 px-3 py-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className={cn(
                      "flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg border",
                      summary.active ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : "border-zinc-800 bg-zinc-900 text-zinc-500",
                    )}>
                      <Globe2 size={15} />
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-sm font-medium text-zinc-100">{summary.label}</span>
                        {summary.active && (
                          <span className="inline-flex items-center gap-1 rounded border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-300">
                            <CheckCircle2 size={11} /> active
                          </span>
                        )}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-zinc-500">
                        <span>{summary.id}</span>
                        {profile.last_url && <span className="max-w-[220px] truncate">{profile.last_url}</span>}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 border-t border-zinc-800 text-[11px] text-zinc-500">
                  <div className="flex min-w-0 items-center gap-1.5 px-3 py-2">
                    <Database size={13} /> <span className="truncate">{summary.storageLabel}</span>
                  </div>
                  <div className="flex min-w-0 items-center gap-1.5 px-3 py-2">
                    <Cookie size={13} /> <span className="truncate">{summary.cookiesLabel}</span>
                  </div>
                </div>

                <footer className="flex flex-wrap justify-end gap-2 border-t border-zinc-800 px-3 py-2">
                  <button
                    type="button"
                    onClick={() => run(profile, "activate")}
                    disabled={busy || summary.active}
                    className="flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                    title="Set active profile"
                  >
                    <Star size={13} /> Active
                  </button>
                  <button
                    type="button"
                    onClick={() => run(profile, "clear_cache")}
                    disabled={busy}
                    className="flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                    title="Clear cache"
                  >
                    <Database size={13} /> Cache
                  </button>
                  <button
                    type="button"
                    onClick={() => run(profile, "clear_cookies")}
                    disabled={busy}
                    className="flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                    title="Clear cookies"
                  >
                    <Cookie size={13} /> Cookies
                  </button>
                  <button
                    type="button"
                    onClick={() => run(profile, "delete")}
                    disabled={busy || summary.id === "default"}
                    className="flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                    title="Delete profile"
                  >
                    <Trash2 size={13} /> Delete
                  </button>
                </footer>
              </article>
            );
          })}
          {summaries.length === 0 && (
            <div className="flex min-h-[160px] items-center justify-center rounded-lg border border-dashed border-zinc-800 text-sm text-zinc-500">
              No browser profiles loaded.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
