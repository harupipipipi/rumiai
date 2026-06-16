import {
  ArrowLeft,
  Braces,
  Check,
  Code2,
  Eye,
  FileText,
  FlaskConical,
  History,
  ListFilter,
  Lock,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  ToggleLeft,
  ToggleRight,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PromptUsageSegmentCard } from "../components/prompts/PromptUsageSegmentCard";
import { statusBadgeClass, tokenText } from "../components/prompts/promptSegmentView";
import { api, type PromptStudioData, type PromptStudioPrompt, type PromptStudioTestResult, type PromptUsageSegment } from "../lib/api";
import { cn } from "../lib/cn";

type StudioTab = "editor" | "test" | "preview" | "diff" | "usage" | "variables";
type PromptFilter = "all" | "active" | "editable" | "readonly" | "overrides";

const tabs: Array<{ id: StudioTab; label: string; icon: typeof Code2 }> = [
  { id: "editor", label: "Editor", icon: Code2 },
  { id: "test", label: "Test", icon: FlaskConical },
  { id: "preview", label: "Preview", icon: Eye },
  { id: "diff", label: "Diff", icon: ListFilter },
  { id: "usage", label: "Usage", icon: FileText },
  { id: "variables", label: "Variables", icon: Braces },
];

const filters: Array<{ id: PromptFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "editable", label: "Editable" },
  { id: "readonly", label: "Read-only" },
  { id: "overrides", label: "Overrides" },
];

function searchParam(name: string): string {
  try {
    return new URLSearchParams(window.location.search).get(name) ?? "";
  } catch {
    return "";
  }
}

function promptKey(prompt?: PromptStudioPrompt | null): string {
  return String(prompt?.prompt_id || prompt?.name || prompt?.id || "").trim();
}

function promptBody(prompt?: PromptStudioPrompt | null): string {
  return String(prompt?.body ?? prompt?.content ?? "");
}

function displaySource(prompt?: PromptStudioPrompt | null): string {
  if (!prompt) return "";
  return String(prompt.effective_source_type || prompt.source_type || prompt.source || "prompt").replace(/_/g, " ");
}

function isOverride(prompt?: PromptStudioPrompt | null): boolean {
  return String(prompt?.source_type ?? prompt?.effective_source_type ?? "") === "profile_override";
}

function listFromUnknown(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function formatInspectorValue(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => typeof item === "object" ? JSON.stringify(item) : String(item)).join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value ?? "");
}

function splitCsvList(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item, index, items) => items.indexOf(item) === index);
}

function verdictTone(status?: string): string {
  if (status === "matched" || status === "selected" || status === "candidate") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-100";
  if (status === "idle" || status === "not-selected" || status === "none") return "border-zinc-800 bg-zinc-950/70 text-zinc-400";
  if (status === "passive") return "border-cyan-500/25 bg-cyan-500/10 text-cyan-100";
  return "border-zinc-800 bg-zinc-950/70 text-zinc-300";
}

function ToolCandidateCard({ item }: { item: Record<string, unknown> }) {
  const why = listFromUnknown(item.why).map(String);
  const matchedFrom = Array.isArray(item.matched_from) ? item.matched_from.join(", ") : String(item.matched_from || "match");
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-zinc-100">{String(item.name || item.tool_id || "Tool")}</div>
          <div className="mt-1 truncate font-mono text-[10px] text-zinc-600">{String(item.tool_id || "")}</div>
        </div>
        <span className="rounded border border-violet-500/25 bg-violet-500/10 px-1.5 py-0.5 font-mono text-[10px] text-violet-100">
          {Number(item.score || 0).toFixed(2)}
        </span>
      </div>
      <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-zinc-400">{String(item.summary || "No summary.")}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <span className="rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 text-[10px] text-zinc-500">{matchedFrom}</span>
        {why.slice(0, 5).map((token) => (
          <span key={token} className="rounded border border-zinc-800 bg-black/25 px-1.5 py-0.5 text-[10px] text-zinc-500">{token}</span>
        ))}
      </div>
    </div>
  );
}

function PromptStudioTestPanel({
  result,
  testInput,
  testTools,
  busy,
  onInputChange,
  onToolsChange,
  onRun,
}: {
  result: PromptStudioTestResult | null;
  testInput: string;
  testTools: string;
  busy: string | null;
  onInputChange: (value: string) => void;
  onToolsChange: (value: string) => void;
  onRun: () => void;
}) {
  const verdicts = result?.verdicts ?? [];
  const matchedSkills = result?.matched_skills ?? [];
  const selectedToolSegments = result?.selected_tool_segments ?? [];
  const candidateSegments = result?.candidate_tool_segments ?? [];
  const candidates = result?.tool_candidates?.combined ?? [];
  const analysis = recordFromUnknown(result?.prompt_tool_analysis);
  const segments = result?.segments ?? [];
  const focusedToolSegments = [...selectedToolSegments, ...candidateSegments].filter((segment, index, items) => (
    items.findIndex((item) => item.id === segment.id && item.status === segment.status) === index
  ));
  return (
    <div className="grid gap-3">
      <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
        <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
          <div className="min-w-0">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-600" htmlFor="prompt-studio-test-input">Test Input</label>
            <textarea
              id="prompt-studio-test-input"
              value={testInput}
              onChange={(event) => onInputChange(event.target.value)}
              className="mt-2 h-28 w-full resize-none rounded-lg border border-zinc-800 bg-black/25 p-3 text-sm leading-relaxed text-zinc-200 outline-none focus:border-zinc-600"
            />
          </div>
          <div className="min-w-0">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-600" htmlFor="prompt-studio-test-tools">Selected Tools</label>
            <textarea
              id="prompt-studio-test-tools"
              value={testTools}
              onChange={(event) => onToolsChange(event.target.value)}
              className="mt-2 h-28 w-full resize-none rounded-lg border border-zinc-800 bg-black/25 p-3 font-mono text-sm leading-relaxed text-zinc-200 outline-none focus:border-zinc-600"
            />
          </div>
          <button
            type="button"
            onClick={onRun}
            disabled={busy === "test"}
            className="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-lg bg-cyan-200 px-3 text-xs font-semibold text-cyan-950 hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-50 lg:mt-6 lg:w-auto"
          >
            <Play size={13} />
            Run Test
          </button>
        </div>
      </section>

      {result && (
        <>
          <section className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            {verdicts.map((verdict) => (
              <div key={verdict.id || verdict.title} className={cn("rounded-lg border p-3", verdictTone(verdict.status))}>
                <div className="text-xs font-semibold">{verdict.title}</div>
                <p className="mt-1 text-[11px] leading-relaxed opacity-80">{verdict.detail}</p>
              </div>
            ))}
          </section>

          <section className="grid gap-3 xl:grid-cols-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="text-xs font-semibold text-zinc-100">Skill Matches</div>
                <span className="font-mono text-[10px] text-zinc-600">{matchedSkills.length}</span>
              </div>
              <div className="grid gap-2">
                {matchedSkills.map((skill, index) => (
                  <div key={`${String(skill.id || "skill")}-${index}`} className="rounded-md border border-zinc-800 bg-black/20 p-2">
                    <div className="truncate text-xs font-semibold text-zinc-200">{String(skill.display_name || skill.id || "Skill")}</div>
                    <div className="mt-1 grid gap-1 text-[11px] text-zinc-500">
                      <div className="truncate">triggers: {formatInspectorValue(skill.triggers)}</div>
                      <div className="truncate">tools: {formatInspectorValue(skill.applies_to_tools)}</div>
                    </div>
                  </div>
                ))}
                {!matchedSkills.length && <div className="rounded-md border border-dashed border-zinc-800 p-4 text-center text-xs text-zinc-500">No skill prompt matched.</div>}
              </div>
              {result.skill_instructions && (
                <pre className="mt-3 max-h-44 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/25 p-3 font-mono text-[12px] leading-relaxed text-zinc-300">{result.skill_instructions}</pre>
              )}
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="text-xs font-semibold text-zinc-100">Tool Decision</div>
                <span className="font-mono text-[10px] text-zinc-600">{candidates.length} candidates</span>
              </div>
              <div className="rounded-md border border-zinc-800/80 bg-black/20 px-2 py-1.5 text-xs leading-relaxed text-zinc-300">
                {String(analysis.decision_boundary || "Prompt text can suggest relevance, but cannot attach or execute tools.")}
              </div>
              <div className="mt-2 grid gap-2">
                {candidates.slice(0, 5).map((candidate) => <ToolCandidateCard key={String(candidate.tool_id || candidate.name)} item={candidate} />)}
                {!candidates.length && <div className="rounded-md border border-dashed border-zinc-800 p-4 text-center text-xs text-zinc-500">No local tool candidate matched.</div>}
              </div>
            </div>
          </section>

          <section className="grid gap-2">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-600">Test Model Input</div>
              <span className="font-mono text-[10px] text-zinc-600">{segments.length} segments</span>
            </div>
            {focusedToolSegments.map((segment) => <PromptUsageSegmentCard key={`${segment.id}-${segment.status}-test-focus`} segment={segment} />)}
            {segments.filter((segment) => segment.kind === "skill").map((segment) => <PromptUsageSegmentCard key={`${segment.id}-${segment.status}-test-skill`} segment={segment} />)}
            {!focusedToolSegments.length && !segments.some((segment) => segment.kind === "skill") && (
              <div className="rounded-lg border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500">No focused skill or tool-schema segment for this test.</div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function promptUsageForPrompt(prompt: PromptStudioPrompt | null | undefined, segments: PromptUsageSegment[]): PromptUsageSegment[] {
  const key = promptKey(prompt);
  if (!key) return [];
  return segments.filter((segment) => {
    const promptId = String(segment.prompt_id || "").trim();
    const id = String(segment.id || "").trim();
    return promptId === key || id === key || id.endsWith(`:${key}`) || id.includes(key);
  });
}

function updateStudioUrl(profileId: string, conversationId: string, promptId: string) {
  const url = new URL(window.location.href);
  url.pathname = "/prompts";
  url.search = "";
  if (profileId) url.searchParams.set("profile_id", profileId);
  if (conversationId) url.searchParams.set("conversation_id", conversationId);
  if (promptId) url.searchParams.set("prompt_id", promptId);
  window.history.replaceState({ promptId }, "", `${url.pathname}${url.search}${url.hash}`);
}

export function PromptStudio() {
  const initialProfileId = searchParam("profile_id");
  const initialConversationId = searchParam("conversation_id");
  const initialPromptId = searchParam("prompt_id");
  const [profileId, setProfileId] = useState(initialProfileId);
  const [conversationId] = useState(initialConversationId);
  const [selectedId, setSelectedId] = useState(initialPromptId);
  const [data, setData] = useState<PromptStudioData | null>(null);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<PromptFilter>("all");
  const [tab, setTab] = useState<StudioTab>("editor");
  const [diffText, setDiffText] = useState("");
  const [lintResult, setLintResult] = useState<Record<string, unknown> | null>(null);
  const [compactResult, setCompactResult] = useState<Record<string, unknown> | null>(null);
  const [testInput, setTestInput] = useState("計算 QA: 12 * 8 を一文で確認して。");
  const [testTools, setTestTools] = useState("");
  const [testResult, setTestResult] = useState<PromptStudioTestResult | null>(null);
  const [busy, setBusy] = useState<string | null>("load");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadStudio = useCallback((promptId?: string) => {
    setBusy("load");
    void api.getPromptStudio({
      profile_id: profileId || undefined,
      conversation_id: conversationId || undefined,
      prompt_id: promptId || undefined,
    })
      .then((result) => {
        const selected = result.selected_prompt ?? result.prompts.find((prompt) => promptKey(prompt) === promptId) ?? result.prompts[0] ?? null;
        const nextPromptId = promptKey(selected);
        setData(result);
        setProfileId(result.profile_id);
        setSelectedId(nextPromptId);
        setDraft(promptBody(selected));
        setDiffText("");
        setLintResult(selected?.lint ?? null);
        setCompactResult(null);
        setError(null);
        updateStudioUrl(result.profile_id, conversationId, nextPromptId);
      })
      .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Prompt Studio could not be loaded."))
      .finally(() => setBusy(null));
  }, [conversationId, profileId]);

  useEffect(() => {
    loadStudio(initialPromptId);
  }, [initialPromptId, loadStudio]);

  const selectedPrompt = useMemo(() => {
    const selected = data?.selected_prompt;
    if (selected && promptKey(selected) === selectedId) return selected;
    return data?.prompts.find((prompt) => promptKey(prompt) === selectedId) ?? selected ?? null;
  }, [data, selectedId]);

  const originalBody = promptBody(selectedPrompt);
  const isDirty = draft !== originalBody;
  const activeSegments = data?.active_summary?.segments ?? [
    ...(data?.active_summary?.active_segments ?? []),
    ...(data?.active_summary?.disabled_segments ?? []),
  ];
  const promptSegments = promptUsageForPrompt(selectedPrompt, activeSegments);
  const sourceChain = listFromUnknown(selectedPrompt?.source_chain);
  const variables = listFromUnknown(selectedPrompt?.variables);
  const validation = recordFromUnknown(selectedPrompt?.validation);
  const lint = lintResult ?? recordFromUnknown(selectedPrompt?.lint);
  const lintWarnings = listFromUnknown(lint.warnings);
  const versions = selectedPrompt?.versions ?? [];
  const compactSuggestion = typeof compactResult?.suggested_prompt === "string" ? compactResult.suggested_prompt : "";
  const safety = recordFromUnknown(selectedPrompt?.safety);
  const safetySummary = typeof safety.summary === "string" ? safety.summary : "";
  const signalTool = recordFromUnknown(selectedPrompt?.tool_signal);
  const signalSkill = recordFromUnknown(selectedPrompt?.skill_signal);
  const canEditDirectly = Boolean(selectedPrompt) && selectedPrompt?.editable !== false && !selectedPrompt?.read_only;
  const canOverridePrompt = Boolean(selectedPrompt?.read_only) && selectedPrompt?.override_allowed !== false;
  const canWriteDraft = canEditDirectly || canOverridePrompt;

  useEffect(() => {
    const toolId = String(signalTool.tool_id || signalTool.tool_name || "").trim();
    if (!toolId) return;
    setTestTools((current) => current.trim() ? current : toolId);
  }, [signalTool.tool_id, signalTool.tool_name]);

  const prompts = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.prompts ?? []).filter((prompt) => {
      if (filter === "active" && prompt.activation_state !== "active") return false;
      if (filter === "editable" && prompt.editable === false) return false;
      if (filter === "readonly" && !prompt.read_only) return false;
      if (filter === "overrides" && !isOverride(prompt)) return false;
      if (!q) return true;
      return [
        prompt.name,
        prompt.id,
        prompt.prompt_id,
        prompt.description,
        prompt.source_type,
        prompt.source,
      ].some((value) => String(value ?? "").toLowerCase().includes(q));
    });
  }, [data?.prompts, filter, query]);

  const selectPrompt = (prompt: PromptStudioPrompt) => {
    const nextId = promptKey(prompt);
    setSelectedId(nextId);
    setDraft(promptBody(prompt));
    setTab("editor");
    setDiffText("");
    setCompactResult(null);
    setTestResult(null);
    setNotice(null);
    updateStudioUrl(profileId, conversationId, nextId);
    loadStudio(nextId);
  };

  const runDiff = () => {
    const promptId = promptKey(selectedPrompt);
    if (!promptId) return;
    setBusy("diff");
    void api.diffPrompt({ profile_id: profileId || undefined, prompt_id: promptId, draft })
      .then((result) => {
        setDiffText(result.diff || "No changes.");
        setTab("diff");
        setError(null);
      })
      .catch((diffError) => setError(diffError instanceof Error ? diffError.message : "Prompt diff failed."))
      .finally(() => setBusy(null));
  };

  const runLint = () => {
    setBusy("lint");
    void api.lintPrompt({ prompt: draft })
      .then((result) => {
        setLintResult(result);
        setTab("variables");
        setError(null);
      })
      .catch((lintError) => setError(lintError instanceof Error ? lintError.message : "Prompt lint failed."))
      .finally(() => setBusy(null));
  };

  const runCompact = () => {
    setBusy("compact");
    void api.compactPrompt({ prompt: draft })
      .then((result) => {
        setCompactResult(result);
        setTab("preview");
        setError(null);
      })
      .catch((compactError) => setError(compactError instanceof Error ? compactError.message : "Prompt compact failed."))
      .finally(() => setBusy(null));
  };

  const runTest = () => {
    const promptId = promptKey(selectedPrompt);
    setBusy("test");
    void api.testPromptStudio({
      profile_id: profileId || undefined,
      conversation_id: conversationId || undefined,
      prompt_id: promptId || undefined,
      draft,
      user_text: testInput,
      selected_tools: splitCsvList(testTools),
    })
      .then((result) => {
        setTestResult(result);
        setTab("test");
        setError(null);
      })
      .catch((testError) => setError(testError instanceof Error ? testError.message : "Prompt Studio test failed."))
      .finally(() => setBusy(null));
  };

  const saveDraft = (forceOverride = false) => {
    const promptId = promptKey(selectedPrompt);
    if (!promptId) return;
    if (!canWriteDraft && !forceOverride) return;
    if (forceOverride && !canOverridePrompt && !canEditDirectly) return;
    setBusy(forceOverride || selectedPrompt?.read_only ? "override" : "save");
    const request = forceOverride || selectedPrompt?.read_only
      ? api.createPromptOverride({ profile_id: profileId || undefined, prompt_id: promptId, body: draft, reason: "studio_override" })
      : api.savePrompt({ profile_id: profileId || undefined, prompt_id: promptId, body: draft, reason: "studio_save" });
    void request
      .then(() => {
        setNotice(forceOverride || selectedPrompt?.read_only ? "Profile override saved." : "Prompt saved.");
        loadStudio(promptId);
      })
      .catch((saveError) => setError(saveError instanceof Error ? saveError.message : "Prompt save failed."))
      .finally(() => setBusy(null));
  };

  const rollback = (versionId: string) => {
    const promptId = promptKey(selectedPrompt);
    if (!promptId || !versionId) return;
    setBusy(`rollback:${versionId}`);
    void api.rollbackPrompt({ profile_id: profileId || undefined, prompt_id: promptId, version_id: versionId })
      .then(() => {
        setNotice("Prompt rolled back.");
        loadStudio(promptId);
      })
      .catch((rollbackError) => setError(rollbackError instanceof Error ? rollbackError.message : "Prompt rollback failed."))
      .finally(() => setBusy(null));
  };

  const toggleSelected = () => {
    const edgeId = String(selectedPrompt?.active_edge_id || "").trim();
    if (!edgeId || selectedPrompt?.allow_disable === false) return;
    const enabled = selectedPrompt?.activation_state !== "active";
    setBusy("toggle");
    void api.togglePromptEdge({
      profile_id: profileId || undefined,
      conversation_id: conversationId || undefined,
      edge_id: edgeId,
      enabled,
    })
      .then(() => {
        setNotice(enabled ? "Prompt enabled." : "Prompt disabled.");
        loadStudio(promptKey(selectedPrompt));
      })
      .catch((toggleError) => setError(toggleError instanceof Error ? toggleError.message : "Prompt toggle failed."))
      .finally(() => setBusy(null));
  };

  const goBack = () => {
    const url = new URL(window.location.href);
    url.pathname = "/chat";
    url.search = "";
    if (conversationId) url.searchParams.set("chat", conversationId);
    window.location.href = `${url.pathname}${url.search}${url.hash}`;
  };

  return (
    <div className="flex h-screen min-h-0 flex-col bg-[#09090b] text-zinc-300">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-zinc-800/70 bg-zinc-950/80 px-3 backdrop-blur">
        <div className="flex min-w-0 items-center gap-2">
          <button type="button" onClick={goBack} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-100" aria-label="Back to chat">
            <ArrowLeft size={16} />
          </button>
          <div className="flex min-w-0 items-center gap-2">
            <SlidersHorizontal size={16} className="shrink-0 text-cyan-300" />
            <h1 className="truncate text-sm font-semibold text-zinc-100">Prompt Studio</h1>
            <span className="hidden rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 font-mono text-[10px] text-zinc-500 sm:inline">
              {profileId || "defaultspack.startup"}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button type="button" onClick={() => loadStudio(selectedId)} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-100" aria-label="Refresh Prompt Studio">
            <RefreshCw size={15} className={cn(busy === "load" && "animate-spin")} />
          </button>
          <button type="button" onClick={runDiff} disabled={!selectedPrompt || busy === "diff" || !canWriteDraft} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-cyan-200 disabled:opacity-40" aria-label="Diff prompt">
            <ListFilter size={15} />
          </button>
          <button type="button" onClick={() => saveDraft(false)} disabled={!selectedPrompt || !isDirty || Boolean(busy) || !canWriteDraft} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white disabled:cursor-not-allowed disabled:opacity-45">
            <Save size={13} />
            {selectedPrompt?.read_only ? (canOverridePrompt ? "Override" : "Read-only") : "Save"}
          </button>
        </div>
      </header>

      {(error || notice) && (
        <div className="shrink-0 border-b border-zinc-800/70 bg-zinc-950 px-4 py-2">
          {error && <div className="rounded-md border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-100">{error}</div>}
          {!error && notice && <div className="rounded-md border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-100">{notice}</div>}
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-[292px_minmax(0,1fr)_340px] overflow-hidden max-[1050px]:grid-cols-[260px_minmax(0,1fr)] max-[780px]:grid-cols-1">
        <aside className="flex min-h-0 flex-col border-r border-zinc-800/70 bg-zinc-950/55 max-[780px]:max-h-[34vh] max-[780px]:border-b max-[780px]:border-r-0">
          <div className="border-b border-zinc-800/70 p-3">
            <div className="relative">
              <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-600" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="h-9 w-full rounded-lg border border-zinc-800 bg-zinc-950 pl-8 pr-3 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
                placeholder="Search prompts"
              />
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {filters.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setFilter(item.id)}
                  className={cn(
                    "rounded-md border px-2 py-1 text-[10px] font-medium transition-colors",
                    filter === item.id
                      ? "border-cyan-500/35 bg-cyan-500/10 text-cyan-100"
                      : "border-zinc-800 bg-zinc-900/45 text-zinc-500 hover:text-zinc-200",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {prompts.map((prompt) => {
              const id = promptKey(prompt);
              const selected = id === selectedId;
              return (
                <button
                  key={`${prompt.source_type}-${id}`}
                  type="button"
                  onClick={() => selectPrompt(prompt)}
                  className={cn(
                    "mb-1.5 w-full rounded-lg border px-3 py-2 text-left transition-colors",
                    selected
                      ? "border-cyan-500/35 bg-cyan-500/10"
                      : "border-zinc-800 bg-zinc-950/45 hover:border-zinc-700 hover:bg-zinc-900/60",
                  )}
                >
                  <div className="flex min-w-0 items-center justify-between gap-2">
                    <span className="min-w-0 truncate text-xs font-semibold text-zinc-100">
                      {String(prompt.metadata?.prompt_usage_segment ? prompt.description || prompt.name || prompt.id : prompt.name || prompt.id).slice(0, 96)}
                    </span>
                    {prompt.read_only ? <Lock size={11} className="shrink-0 text-zinc-600" /> : <Check size={11} className="shrink-0 text-emerald-300" />}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    <span className={cn("rounded border px-1.5 py-0.5 text-[9px]", statusBadgeClass(prompt.activation_state))}>{prompt.activation_state || "available"}</span>
                    <span className="rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 text-[9px] text-zinc-500">{displaySource(prompt)}</span>
                    {isOverride(prompt) && <span className="rounded border border-cyan-500/25 bg-cyan-500/10 px-1.5 py-0.5 text-[9px] text-cyan-200">override</span>}
                  </div>
                  <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-zinc-500">{prompt.description || prompt.preview || "Prompt"}</p>
                </button>
              );
            })}
            {!prompts.length && <div className="rounded-lg border border-dashed border-zinc-800 p-4 text-center text-xs text-zinc-500">No prompts match.</div>}
          </div>
        </aside>

        <main className="flex min-h-0 min-w-0 flex-col bg-[#09090b]">
          <div className="border-b border-zinc-800/70 px-4 py-3">
            <div className="flex min-w-0 items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <h2 className="truncate text-base font-semibold text-zinc-100">{selectedPrompt?.name || "Prompt"}</h2>
                  <span className={cn("rounded border px-1.5 py-0.5 text-[10px]", statusBadgeClass(selectedPrompt?.activation_state))}>
                    {selectedPrompt?.activation_state || "available"}
                  </span>
                  <span className="rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 text-[10px] text-zinc-500">{tokenText(selectedPrompt?.tokens)}</span>
                </div>
                <p className="mt-1 truncate text-xs text-zinc-500">{selectedPrompt?.description || selectedPrompt?.source || "Prompt source"}</p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button type="button" onClick={runLint} disabled={!selectedPrompt || busy === "lint"} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-100 disabled:opacity-40" aria-label="Lint prompt">
                  <ShieldCheck size={15} />
                </button>
                <button type="button" onClick={runTest} disabled={!selectedPrompt || busy === "test"} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-cyan-200 disabled:opacity-40" aria-label="Run Studio test">
                  <FlaskConical size={15} />
                </button>
                <button type="button" onClick={runCompact} disabled={!selectedPrompt || busy === "compact" || !canWriteDraft} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-100 disabled:opacity-40" aria-label="Compact prompt">
                  <Wand2 size={15} />
                </button>
                <button type="button" onClick={() => saveDraft(true)} disabled={!selectedPrompt || Boolean(busy) || (!canOverridePrompt && !canEditDirectly)} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-cyan-200 disabled:opacity-40" aria-label="Create profile override">
                  <SlidersHorizontal size={15} />
                </button>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-1">
              {tabs.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setTab(item.id)}
                    className={cn(
                      "inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium",
                      tab === item.id
                        ? "border-zinc-600 bg-zinc-900 text-zinc-100"
                        : "border-zinc-800 bg-zinc-950/60 text-zinc-500 hover:text-zinc-200",
                    )}
                  >
                    <Icon size={13} />
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-auto p-4">
            {tab === "editor" && (
              <textarea
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value);
                  setNotice(null);
                }}
                readOnly={!canWriteDraft}
                spellCheck={false}
                className={cn(
                  "min-h-[calc(100vh-210px)] w-full resize-none rounded-lg border border-zinc-800 bg-zinc-950/75 p-4 font-mono text-[13px] leading-relaxed text-zinc-200 outline-none focus:border-zinc-600",
                  !canWriteDraft && "cursor-default text-zinc-400 focus:border-zinc-800",
                )}
              />
            )}

            {tab === "preview" && (
              <div className="grid gap-3">
                {compactSuggestion && (
                  <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/10 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-xs font-semibold text-cyan-100">Compacted Draft</div>
                      <button type="button" onClick={() => setDraft(compactSuggestion)} className="rounded-md bg-cyan-200 px-2 py-1 text-[11px] font-semibold text-cyan-950">
                        Apply
                      </button>
                    </div>
                    <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap font-mono text-[12px] leading-relaxed text-cyan-50">{compactSuggestion}</pre>
                  </div>
                )}
                <pre className="min-h-[calc(100vh-240px)] whitespace-pre-wrap rounded-lg border border-zinc-800 bg-zinc-950/75 p-4 font-mono text-[13px] leading-relaxed text-zinc-200">
                  {draft || "Empty prompt."}
                </pre>
              </div>
            )}

            {tab === "test" && (
              <PromptStudioTestPanel
                result={testResult}
                testInput={testInput}
                testTools={testTools}
                busy={busy}
                onInputChange={(value) => {
                  setTestInput(value);
                  setNotice(null);
                }}
                onToolsChange={(value) => {
                  setTestTools(value);
                  setNotice(null);
                }}
                onRun={runTest}
              />
            )}

            {tab === "diff" && (
              <pre className="min-h-[calc(100vh-210px)] whitespace-pre-wrap rounded-lg border border-zinc-800 bg-zinc-950/75 p-4 font-mono text-[12px] leading-relaxed text-zinc-300">
                {diffText || "Run diff to compare the draft against its base prompt."}
              </pre>
            )}

            {tab === "usage" && (
              <div className="grid gap-3">
                <section className="grid gap-2">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-600">Selected Prompt Usage</div>
                  {promptSegments.map((segment) => <PromptUsageSegmentCard key={`${segment.id}-${segment.status}-selected`} segment={segment} />)}
                  {!promptSegments.length && <div className="rounded-lg border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500">No recorded usage for this prompt in the active graph.</div>}
                </section>
                <section className="grid gap-2">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-600">Current Model Input</div>
                    <span className="font-mono text-[10px] text-zinc-600">{activeSegments.length} segments</span>
                  </div>
                  {activeSegments.map((segment) => <PromptUsageSegmentCard key={`${segment.id}-${segment.status}-all`} segment={segment} />)}
                  {!activeSegments.length && <div className="rounded-lg border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500">No model input segments are available.</div>}
                </section>
              </div>
            )}

            {tab === "variables" && (
              <div className="grid gap-3">
                <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                  <h3 className="text-xs font-semibold text-zinc-100">Variables</h3>
                  <pre className="mt-2 overflow-auto rounded-md bg-black/25 p-3 font-mono text-[12px] text-zinc-300">{variables.length ? prettyJson(variables) : "[]"}</pre>
                </section>
                <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                  <h3 className="text-xs font-semibold text-zinc-100">Validation</h3>
                  <pre className="mt-2 overflow-auto rounded-md bg-black/25 p-3 font-mono text-[12px] text-zinc-300">{prettyJson(validation)}</pre>
                </section>
                <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                  <h3 className="text-xs font-semibold text-zinc-100">Lint</h3>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {lintWarnings.map((warning, index) => (
                      <span key={`${String(warning)}-${index}`} className="rounded border border-amber-500/25 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-100">{String(warning)}</span>
                    ))}
                    {!lintWarnings.length && <span className="rounded border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-100">clean</span>}
                  </div>
                  <pre className="mt-2 overflow-auto rounded-md bg-black/25 p-3 font-mono text-[12px] text-zinc-300">{prettyJson(lint)}</pre>
                </section>
              </div>
            )}
          </div>
        </main>

        <aside className="flex min-h-0 flex-col border-l border-zinc-800/70 bg-zinc-950/55 max-[1050px]:col-span-2 max-[1050px]:max-h-[38vh] max-[1050px]:border-l-0 max-[1050px]:border-t max-[780px]:col-span-1">
          <div className="flex items-center justify-between border-b border-zinc-800/70 px-4 py-3">
            <div className="text-sm font-semibold text-zinc-100">Inspector</div>
            {selectedPrompt?.active_edge_id && (
              <button
                type="button"
                onClick={toggleSelected}
                disabled={selectedPrompt.allow_disable === false || busy === "toggle"}
                className={cn(
                  "rounded-md p-1.5",
                  selectedPrompt.allow_disable === false ? "cursor-not-allowed text-zinc-700" : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-100",
                )}
                aria-label={selectedPrompt.activation_state === "active" ? "Disable prompt" : "Enable prompt"}
              >
                {selectedPrompt.allow_disable === false ? <Lock size={15} /> : selectedPrompt.activation_state === "active" ? <ToggleRight size={17} /> : <ToggleLeft size={17} />}
              </button>
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            <div className="grid gap-3">
              <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-100">
                  <FileText size={13} className="text-cyan-300" />
                  Source
                </div>
                <dl className="space-y-2 text-[11px]">
                  <div className="flex justify-between gap-3">
                    <dt className="text-zinc-500">Type</dt>
                    <dd className="text-right text-zinc-200">{displaySource(selectedPrompt)}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-zinc-500">Editable</dt>
                    <dd className="text-right text-zinc-200">{selectedPrompt?.editable ? "yes" : canOverridePrompt ? "override only" : "inspect only"}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-zinc-500">Tokens</dt>
                    <dd className="text-right text-zinc-200">{tokenText(selectedPrompt?.tokens)}</dd>
                  </div>
                </dl>
              </section>

              <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-100">
                  <ShieldCheck size={13} className="text-emerald-300" />
                  Safety Boundary
                </div>
                <div className="grid gap-1.5">
                  {safetySummary && <p className="mb-1 text-[11px] leading-relaxed text-zinc-400">{safetySummary}</p>}
                  {Object.entries(Object.keys(safety).length ? safety : {
                    passive_text_only: true,
                    can_grant_permissions: false,
                    can_call_tools: false,
                    can_mutate_chat_state: false,
                  }).filter(([key]) => key !== "summary").map(([key, value]) => (
                    <div key={key} className="flex items-center justify-between gap-2 text-[11px]">
                      <span className="text-zinc-500">{key.replace(/_/g, " ")}</span>
                      <span className={value === true ? "text-emerald-300" : "text-zinc-400"}>{value === true ? "yes" : value === false ? "no" : String(value)}</span>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-100">
                  <SlidersHorizontal size={13} className="text-cyan-300" />
                  Activation
                </div>
                <div className="space-y-2 text-[11px] text-zinc-500">
                  <div className="flex items-center justify-between gap-2">
                    <span>State</span>
                    <span className={cn("rounded border px-1.5 py-0.5", statusBadgeClass(selectedPrompt?.activation_state))}>{selectedPrompt?.activation_state || "available"}</span>
                  </div>
                  <div className="break-all font-mono text-zinc-600">{selectedPrompt?.active_edge_id || "no active edge"}</div>
                  <p className="leading-relaxed">{selectedPrompt?.active_reason || "Available in Prompt Studio."}</p>
                  {selectedPrompt?.input_role && <p className="leading-relaxed text-zinc-400">{selectedPrompt.input_role}</p>}
                  {selectedPrompt?.source_priority && <p className="leading-relaxed">{selectedPrompt.source_priority}</p>}
                </div>
              </section>

              {(Object.keys(signalTool).length > 0 || Object.keys(signalSkill).length > 0) && (
                <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-100">
                    <Wand2 size={13} className="text-violet-300" />
                    Tool / Skill Signal
                  </div>
                  <div className="space-y-2 text-[11px] text-zinc-500">
                    {Object.entries(signalTool).map(([key, value]) => (
                      <div key={key} className="flex justify-between gap-3">
                        <span>{key.replace(/_/g, " ")}</span>
                        <span className="min-w-0 truncate text-right text-zinc-300">{formatInspectorValue(value)}</span>
                      </div>
                    ))}
                    {Object.entries(signalSkill).map(([key, value]) => (
                      <div key={key} className="flex justify-between gap-3">
                        <span>{key.replace(/_/g, " ")}</span>
                        <span className="min-w-0 truncate text-right text-zinc-300">{formatInspectorValue(value)}</span>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-100">
                  <History size={13} className="text-zinc-300" />
                  Source Chain
                </div>
                <div className="grid gap-2">
                  {sourceChain.map((source, index) => (
                    <div key={index} className="rounded-md border border-zinc-800 bg-black/20 p-2 text-[11px] text-zinc-400">
                      <pre className="whitespace-pre-wrap break-all font-mono">{prettyJson(source)}</pre>
                    </div>
                  ))}
                  {!sourceChain.length && <div className="text-[11px] text-zinc-600">No source chain recorded.</div>}
                </div>
              </section>

              <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-100">
                  <RotateCcw size={13} className="text-zinc-300" />
                  Versions
                </div>
                <div className="grid gap-2">
                  {versions.map((version) => (
                    <div key={version.version_id} className="rounded-md border border-zinc-800 bg-black/20 p-2">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate font-mono text-[10px] text-zinc-300">{version.version_id}</div>
                          <div className="mt-1 text-[10px] text-zinc-600">{version.created_at || version.scope}</div>
                        </div>
                        <button
                          type="button"
                          onClick={() => rollback(version.version_id)}
                          disabled={busy === `rollback:${version.version_id}`}
                          className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-100 disabled:opacity-40"
                          aria-label="Rollback prompt version"
                        >
                          <RotateCcw size={13} />
                        </button>
                      </div>
                      {version.reason && <div className="mt-1 text-[10px] text-zinc-500">{version.reason}</div>}
                    </div>
                  ))}
                  {!versions.length && <div className="text-[11px] text-zinc-600">No saved versions yet.</div>}
                </div>
              </section>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
