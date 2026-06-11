import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Check,
  Copy,
  FilePenLine,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import {
  systemPromptResources,
  type SystemPromptListResponse,
  type SystemPromptRecord,
} from "../features/systemPrompts/resources/systemPromptResources";

type BusyState = "load" | "save" | "activate" | "delete" | null;

type PromptDraft = {
  name: string;
  description: string;
  body: string;
  tags: string;
};

const blankDraft: PromptDraft = {
  name: "System Prompt",
  description: "",
  body: "",
  tags: "system",
};

function promptBody(prompt: SystemPromptRecord | null | undefined): string {
  return String(prompt?.body ?? prompt?.content ?? "");
}

function draftFromPrompt(prompt: SystemPromptRecord): PromptDraft {
  return {
    name: prompt.name || prompt.id || "System Prompt",
    description: prompt.description ?? "",
    body: promptBody(prompt),
    tags: (prompt.tags ?? []).join(", "),
  };
}

function tagsFromDraft(value: string): string[] {
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function matchesPrompt(prompt: SystemPromptRecord, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [
    prompt.id,
    prompt.name,
    prompt.description,
    prompt.source,
    ...(prompt.tags ?? []),
  ].some((value) => String(value ?? "").toLowerCase().includes(needle));
}

function formatSource(prompt: SystemPromptRecord): string {
  if (prompt.source_pack_id) return prompt.source_pack_id;
  if (prompt.source) return prompt.source;
  return prompt.read_only ? "built-in" : "user";
}

function estimateTokens(content: string): number {
  return Math.max(0, Math.round(content.length / 4));
}

function applyListResponse(
  response: SystemPromptListResponse,
  preferredId: string | null | undefined,
  currentId: string | null,
): { prompts: SystemPromptRecord[]; activeId: string; selectedId: string | null; draft: PromptDraft } {
  const prompts = response.prompts ?? [];
  const activeId = response.active_id ?? "";
  const preferred = preferredId || response.prompt?.id || currentId || activeId || prompts[0]?.id || null;
  const selected = prompts.find((prompt) => prompt.id === preferred) ?? prompts.find((prompt) => prompt.active) ?? prompts[0] ?? null;
  return {
    prompts,
    activeId,
    selectedId: selected?.id ?? null,
    draft: selected ? draftFromPrompt(selected) : blankDraft,
  };
}

export function SystemPromptManager() {
  const [prompts, setPrompts] = useState<SystemPromptRecord[]>([]);
  const [activeId, setActiveId] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<PromptDraft>(blankDraft);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<BusyState>("load");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const selectedPrompt = useMemo(
    () => prompts.find((prompt) => prompt.id === selectedId) ?? null,
    [prompts, selectedId],
  );
  const filteredPrompts = useMemo(
    () => prompts.filter((prompt) => matchesPrompt(prompt, query)),
    [prompts, query],
  );
  const bodyStats = useMemo(() => ({
    chars: draft.body.length,
    tokens: estimateTokens(draft.body),
  }), [draft.body]);
  const isReadOnly = Boolean(selectedPrompt?.read_only);
  const isNew = selectedId === null;
  const isDirty = useMemo(() => {
    if (!selectedPrompt) return Boolean(draft.name.trim() || draft.description.trim() || draft.body.trim());
    const original = draftFromPrompt(selectedPrompt);
    return (
      draft.name !== original.name
      || draft.description !== original.description
      || draft.body !== original.body
      || draft.tags !== original.tags
    );
  }, [draft, selectedPrompt]);
  const canWrite = Boolean(draft.name.trim()) && busy === null;
  const saveLabel = isReadOnly ? "Copy" : "Save";

  const syncFromResponse = useCallback((response: SystemPromptListResponse, preferredId?: string | null) => {
    const next = applyListResponse(response, preferredId, selectedId);
    setPrompts(next.prompts);
    setActiveId(next.activeId);
    setSelectedId(next.selectedId);
    setDraft(next.draft);
  }, [selectedId]);

  const loadPrompts = useCallback(async (preferredId?: string | null) => {
    setBusy("load");
    setError("");
    try {
      const response = await systemPromptResources.list();
      const next = applyListResponse(response, preferredId, selectedId);
      setPrompts(next.prompts);
      setActiveId(next.activeId);
      setSelectedId(next.selectedId);
      setDraft(next.draft);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load system prompts");
    } finally {
      setBusy(null);
    }
  }, [selectedId]);

  useEffect(() => {
    let mounted = true;
    setBusy("load");
    systemPromptResources.list()
      .then((response) => {
        if (!mounted) return;
        const next = applyListResponse(response, null, null);
        setPrompts(next.prompts);
        setActiveId(next.activeId);
        setSelectedId(next.selectedId);
        setDraft(next.draft);
      })
      .catch((err) => {
        if (mounted) setError(err instanceof Error ? err.message : "Failed to load system prompts");
      })
      .finally(() => {
        if (mounted) setBusy(null);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const selectPrompt = (prompt: SystemPromptRecord) => {
    setSelectedId(prompt.id);
    setDraft(draftFromPrompt(prompt));
    setError("");
  };

  const startNewPrompt = () => {
    setSelectedId(null);
    setDraft(blankDraft);
    setError("");
  };

  const buildPayload = (activate = false) => ({
    name: draft.name.trim() || "System Prompt",
    description: draft.description.trim(),
    body: draft.body,
    content: draft.body,
    tags: tagsFromDraft(draft.tags),
    metadata: {
      kind: "system_prompt",
      source: "user",
    },
    activate,
  });

  const savePrompt = async (activate = false) => {
    if (!draft.name.trim()) {
      setError("Name is required.");
      return null;
    }
    setBusy(activate ? "activate" : "save");
    setError("");
    try {
      let response: SystemPromptListResponse;
      const payload = buildPayload(activate);
      if (selectedPrompt && !selectedPrompt.read_only) {
        response = await systemPromptResources.update(selectedPrompt.id, payload);
      } else {
        response = await systemPromptResources.create(payload);
      }
      const savedId = response.prompt?.id || selectedPrompt?.id || response.prompts?.find((prompt) => prompt.name === payload.name)?.id || null;
      if (activate && savedId && !response.prompts?.find((prompt) => prompt.id === savedId)?.active) {
        response = await systemPromptResources.activate(savedId);
      }
      syncFromResponse(response, savedId);
      return savedId;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save system prompt");
      return null;
    } finally {
      setBusy(null);
    }
  };

  const activatePrompt = async () => {
    if (!selectedPrompt || isDirty || isReadOnly && draft.body !== promptBody(selectedPrompt)) {
      await savePrompt(true);
      return;
    }
    setBusy("activate");
    setError("");
    try {
      const response = await systemPromptResources.activate(selectedPrompt.id);
      syncFromResponse(response, selectedPrompt.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to activate system prompt");
    } finally {
      setBusy(null);
    }
  };

  const deletePrompt = async () => {
    if (!selectedPrompt || selectedPrompt.read_only) return;
    setBusy("delete");
    setError("");
    try {
      const response = await systemPromptResources.remove(selectedPrompt.id);
      syncFromResponse(response, null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete system prompt");
    } finally {
      setBusy(null);
    }
  };

  const copySelectedId = async () => {
    if (!selectedPrompt?.id) return;
    try {
      await navigator.clipboard?.writeText(selectedPrompt.id);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className="flex h-full min-h-0 flex-col bg-zinc-950 text-zinc-100">
      <header className="flex flex-shrink-0 items-center justify-between gap-3 border-b border-zinc-800/80 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/10 text-violet-200">
              <Sparkles size={15} />
            </span>
            <div className="min-w-0">
              <h2 className="truncate text-[13px] font-semibold tracking-normal text-zinc-100">System Prompts</h2>
              <p className="truncate text-[10px] text-zinc-500">{prompts.length} profiles</p>
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={() => loadPrompts(selectedId)}
          disabled={busy !== null}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-zinc-500 transition-colors hover:bg-zinc-900 hover:text-zinc-200 disabled:opacity-50"
          title="Refresh"
        >
          {busy === "load" ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
        <div className="flex flex-shrink-0 items-center gap-2 rounded-lg bg-zinc-900/80 px-3 py-2 text-zinc-400">
          <Search size={14} className="flex-shrink-0" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search prompts"
            className="min-w-0 flex-1 bg-transparent text-[12px] text-zinc-200 outline-none placeholder:text-zinc-600"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="text-zinc-600 hover:text-zinc-300"
              title="Clear search"
            >
              <X size={13} />
            </button>
          )}
        </div>

        <div className="grid flex-shrink-0 grid-cols-1 gap-1.5">
          <button
            type="button"
            onClick={startNewPrompt}
            className="flex items-center justify-between rounded-lg bg-zinc-900/70 px-3 py-2 text-left text-[12px] text-zinc-300 transition-colors hover:bg-zinc-900 hover:text-zinc-100"
          >
            <span className="flex min-w-0 items-center gap-2">
              <Plus size={14} className="text-emerald-300" />
              <span className="truncate">New prompt</span>
            </span>
          </button>
          <div className="max-h-48 overflow-y-auto rounded-lg bg-zinc-900/35 p-1">
            {filteredPrompts.map((prompt) => {
              const active = prompt.active || prompt.id === activeId;
              const selected = prompt.id === selectedId;
              return (
                <button
                  key={prompt.id}
                  type="button"
                  onClick={() => selectPrompt(prompt)}
                  className={[
                    "flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left transition-colors",
                    selected ? "bg-zinc-800 text-zinc-100" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200",
                  ].join(" ")}
                >
                  <span className={[
                    "mt-0.5 h-2 w-2 flex-shrink-0 rounded-full",
                    active ? "bg-emerald-300" : "bg-zinc-700",
                  ].join(" ")} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12px] font-medium">{prompt.name || prompt.id}</span>
                    <span className="block truncate text-[10px] text-zinc-500">{formatSource(prompt)}</span>
                  </span>
                  {prompt.read_only && <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[9px] text-zinc-500">RO</span>}
                </button>
              );
            })}
            {filteredPrompts.length === 0 && (
              <div className="px-3 py-5 text-center text-[11px] text-zinc-600">No matches</div>
            )}
          </div>
        </div>

        <div className="min-h-0 flex-1 rounded-xl bg-zinc-900/45 p-3">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-zinc-950 text-violet-200">
                <FilePenLine size={14} />
              </span>
              <div className="min-w-0">
                <p className="truncate text-[12px] font-semibold text-zinc-100">{isNew ? "Draft" : selectedPrompt?.name}</p>
                <p className="truncate text-[10px] text-zinc-500">{isReadOnly ? "Save creates a user copy" : "User editable"}</p>
              </div>
            </div>
            {selectedPrompt?.id && (
              <button
                type="button"
                onClick={copySelectedId}
                className="flex h-7 w-7 items-center justify-center rounded-lg text-zinc-500 hover:bg-zinc-950 hover:text-zinc-200"
                title="Copy prompt id"
              >
                {copied ? <Check size={13} className="text-emerald-300" /> : <Copy size={13} />}
              </button>
            )}
          </div>

          <label className="mb-2 block">
            <span className="mb-1 block text-[10px] font-medium uppercase text-zinc-500">Name</span>
            <input
              value={draft.name}
              onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
              className="w-full rounded-lg bg-zinc-950 px-3 py-2 text-[12px] text-zinc-100 outline-none ring-1 ring-zinc-800 transition focus:ring-violet-500/60"
            />
          </label>

          <label className="mb-2 block">
            <span className="mb-1 block text-[10px] font-medium uppercase text-zinc-500">Description</span>
            <input
              value={draft.description}
              onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))}
              className="w-full rounded-lg bg-zinc-950 px-3 py-2 text-[12px] text-zinc-100 outline-none ring-1 ring-zinc-800 transition focus:ring-violet-500/60"
              placeholder="Short purpose"
            />
          </label>

          <label className="mb-2 block">
            <span className="mb-1 block text-[10px] font-medium uppercase text-zinc-500">Tags</span>
            <input
              value={draft.tags}
              onChange={(event) => setDraft((current) => ({ ...current, tags: event.target.value }))}
              className="w-full rounded-lg bg-zinc-950 px-3 py-2 text-[12px] text-zinc-100 outline-none ring-1 ring-zinc-800 transition focus:ring-violet-500/60"
              placeholder="system, concise"
            />
          </label>

          <label className="block">
            <span className="mb-1 flex items-center justify-between gap-2 text-[10px] font-medium uppercase text-zinc-500">
              <span>Prompt</span>
              <span className="normal-case text-zinc-600">{bodyStats.chars} chars / {bodyStats.tokens} tokens</span>
            </span>
            <textarea
              value={draft.body}
              onChange={(event) => setDraft((current) => ({ ...current, body: event.target.value }))}
              className="min-h-52 w-full resize-y rounded-lg bg-zinc-950 px-3 py-2 font-mono text-[11px] leading-5 text-zinc-100 outline-none ring-1 ring-zinc-800 transition focus:ring-violet-500/60"
              spellCheck={false}
            />
          </label>
        </div>

        {error && (
          <div className="rounded-lg bg-red-500/10 px-3 py-2 text-[11px] text-red-200">
            {error}
          </div>
        )}
      </div>

      <footer className="flex flex-shrink-0 items-center gap-2 border-t border-zinc-800/80 px-3 py-3">
        <button
          type="button"
          onClick={() => savePrompt(false)}
          disabled={!canWrite}
          className="flex min-w-0 flex-1 items-center justify-center gap-2 rounded-lg bg-zinc-100 px-3 py-2 text-[12px] font-semibold text-zinc-950 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
          title={isReadOnly ? "Save copy" : "Save"}
        >
          {busy === "save" ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          <span className="truncate">{saveLabel}</span>
        </button>
        <button
          type="button"
          onClick={activatePrompt}
          disabled={busy !== null || (!selectedPrompt && !draft.body.trim())}
          className="flex min-w-0 flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-400 px-3 py-2 text-[12px] font-semibold text-zinc-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy === "activate" ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
          <span className="truncate">Activate</span>
        </button>
        <button
          type="button"
          onClick={deletePrompt}
          disabled={busy !== null || !selectedPrompt || selectedPrompt.read_only}
          className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg text-zinc-500 transition hover:bg-red-500/10 hover:text-red-200 disabled:cursor-not-allowed disabled:opacity-30"
          title="Delete"
        >
          <Trash2 size={14} />
        </button>
      </footer>
    </section>
  );
}

export default SystemPromptManager;
