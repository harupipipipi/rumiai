import { useMemo, useState, type FormEvent } from "react";
import { CheckCircle2, KeyRound, Plus, RefreshCw, Trash2, Wand2, XCircle } from "lucide-react";

import { api, type ApiKeySummary, type SaveApiKeyRequest } from "../lib/api";
import { cn } from "../lib/cn";

export function safeApiKeyDisplay(key: ApiKeySummary): string {
  if (!key.configured) return "Not set";
  if (key.redacted && /^[A-Za-z0-9_-]{0,8}\*{2,}[A-Za-z0-9_-]{0,8}$/.test(key.redacted)) {
    return key.redacted;
  }
  return "Saved";
}

export function apiKeySortKey(key: ApiKeySummary): string {
  return `${key.configured ? "0" : "1"}:${key.provider_id}:${key.label || key.id}`;
}

export function ApiKeyManager({
  keys,
  providers = ["openrouter", "google"],
  loading = false,
  onRefresh,
  onSave,
  onDelete,
  onTest,
}: {
  keys: ApiKeySummary[];
  providers?: string[];
  loading?: boolean;
  onRefresh?: () => void;
  onSave?: (payload: SaveApiKeyRequest) => Promise<ApiKeySummary | void> | ApiKeySummary | void;
  onDelete?: (key: ApiKeySummary) => Promise<void> | void;
  onTest?: (key: ApiKeySummary) => Promise<{ ok: boolean; message?: string } | void> | { ok: boolean; message?: string } | void;
}) {
  const sortedKeys = useMemo(() => [...keys].sort((a, b) => apiKeySortKey(a).localeCompare(apiKeySortKey(b))), [keys]);
  const [providerId, setProviderId] = useState(providers[0] ?? "");
  const [label, setLabel] = useState("");
  const [value, setValue] = useState("");
  const [message, setMessage] = useState("");
  const [busyKeyId, setBusyKeyId] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!providerId || !value.trim()) return;
    setSaving(true);
    setMessage("");
    try {
      const payload: SaveApiKeyRequest = {
        provider_id: providerId,
        label: label.trim() || undefined,
        value,
        make_default: true,
      };
      if (onSave) {
        await onSave(payload);
      } else {
        await api.saveApiKey(payload);
      }
      setValue("");
      setLabel("");
      setMessage("Saved");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const deleteKey = async (key: ApiKeySummary) => {
    setBusyKeyId(key.id);
    setMessage("");
    try {
      if (onDelete) {
        await onDelete(key);
      } else {
        await api.deleteApiKey(key.id);
      }
      setMessage("Deleted");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Delete failed");
    } finally {
      setBusyKeyId("");
    }
  };

  const testKey = async (key: ApiKeySummary) => {
    setBusyKeyId(key.id);
    setMessage("");
    try {
      const result = onTest ? await onTest(key) : await api.testApiKey(key.id);
      setMessage(result?.message || (result?.ok === false ? "Test failed" : "Test passed"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Test failed");
    } finally {
      setBusyKeyId("");
    }
  };

  return (
    <section className="flex h-full min-h-0 flex-col bg-[#09090b] text-zinc-100">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">API Keys</h2>
          <p className="mt-0.5 truncate text-[11px] text-zinc-500">{sortedKeys.filter((key) => key.configured).length} configured</p>
        </div>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
            title="Refresh API keys"
          >
            <RefreshCw size={14} /> Refresh
          </button>
        )}
      </header>

      <form onSubmit={save} className="grid gap-2 border-b border-zinc-800 p-4 md:grid-cols-[160px_1fr_1.4fr_auto]">
        <select
          value={providerId}
          onChange={(event) => setProviderId(event.target.value)}
          className="h-9 rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
        >
          {providers.map((provider) => (
            <option key={provider} value={provider}>
              {provider}
            </option>
          ))}
        </select>
        <input
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Label"
          className="h-9 rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
        />
        <input
          type="password"
          autoComplete="off"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="New key"
          className="h-9 rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
        />
        <button
          type="submit"
          disabled={!value.trim() || saving}
          className="flex h-9 items-center justify-center gap-1.5 rounded-md bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white disabled:opacity-50"
          title="Save API key"
        >
          <Plus size={14} /> Save
        </button>
      </form>

      {message && <div className="border-b border-zinc-800 px-4 py-2 text-xs text-zinc-400">{message}</div>}

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="grid gap-2">
          {sortedKeys.map((key) => {
            const busy = busyKeyId === key.id;
            return (
              <article key={key.id} className="rounded-lg border border-zinc-800 bg-zinc-950/60">
                <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className={cn(
                      "flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg border",
                      key.configured ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : "border-zinc-800 bg-zinc-900 text-zinc-500",
                    )}>
                      <KeyRound size={15} />
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-sm font-medium text-zinc-100">{key.label || key.provider_id}</span>
                        <span className="rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 text-[10px] text-zinc-500">
                          {key.provider_id}
                        </span>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-zinc-500">
                        <span>{safeApiKeyDisplay(key)}</span>
                        {key.key_name && <span>{key.key_name}</span>}
                        {key.last_used_at && <span>used {String(key.last_used_at)}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={cn(
                      "inline-flex h-7 items-center gap-1 rounded-md border px-2 text-[11px]",
                      key.configured ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300" : "border-zinc-800 bg-zinc-900 text-zinc-500",
                    )}>
                      {key.configured ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                      {key.configured ? "ready" : "missing"}
                    </span>
                    <button
                      type="button"
                      onClick={() => testKey(key)}
                      disabled={!key.configured || busy}
                      className="flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                      title="Test key"
                    >
                      <Wand2 size={13} /> Test
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteKey(key)}
                      disabled={busy}
                      className="flex h-7 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-[11px] text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
                      title="Delete key"
                    >
                      <Trash2 size={13} /> Delete
                    </button>
                  </div>
                </div>
                {(key.scopes?.length || key.models?.length) && (
                  <div className="flex flex-wrap gap-1 border-t border-zinc-800 px-3 py-2">
                    {[...(key.scopes ?? []), ...(key.models ?? [])].slice(0, 8).map((item) => (
                      <span key={item} className="rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 text-[10px] text-zinc-500">
                        {item}
                      </span>
                    ))}
                  </div>
                )}
              </article>
            );
          })}
          {sortedKeys.length === 0 && (
            <div className="flex min-h-[140px] items-center justify-center rounded-lg border border-dashed border-zinc-800 text-sm text-zinc-500">
              No key metadata loaded.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
