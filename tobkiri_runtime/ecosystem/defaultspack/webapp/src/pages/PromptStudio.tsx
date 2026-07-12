import {
  AlertTriangle,
  ArrowLeft,
  Braces,
  Check,
  Code2,
  Cpu,
  FileText,
  FlaskConical,
  History,
  Info,
  Languages,
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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PromptUsageSegmentCard } from "../components/prompts/PromptUsageSegmentCard";
import { statusBadgeClass, tokenText, tokenizerLabel, tokenizerNeedsWarning, tokenizerWarningText } from "../components/prompts/promptSegmentView";
import { api, type ModelProfile, type PromptStudioData, type PromptStudioPrompt, type PromptStudioTestResult, type PromptUsageSegment, type TemplateCatalogMetadataItem, type TokenizerInfo, type UICatalog } from "../lib/api";
import { cn } from "../lib/cn";
import { isLocaleSetting, normalizeLocale, supportedLocales, t, type LocaleSetting } from "../lib/i18n";
import {
  selectTemplateAiInput,
  selectTemplateToolPolicy,
  templateAiInputSourceIds,
  templateToolPolicyReferencePayload,
  templateToolPolicySettings,
  templateToolPolicySourceIds,
  type TemplateToolPolicySettings,
} from "../lib/templateAiInput";

type InspectorTab = "selected" | "test" | "diff" | "usage" | "variables";
type PromptFilter = "all" | "active" | "editable" | "readonly" | "overrides";

const inspectorTabs: Array<{ id: InspectorTab; labelKey: Parameters<typeof t>[1]; icon: typeof Code2 }> = [
  { id: "selected", labelKey: "promptStudio.tab.selected", icon: Info },
  { id: "test", labelKey: "promptStudio.tab.test", icon: FlaskConical },
  { id: "diff", labelKey: "promptStudio.tab.diff", icon: ListFilter },
  { id: "usage", labelKey: "promptStudio.tab.usage", icon: FileText },
  { id: "variables", labelKey: "promptStudio.tab.variables", icon: Braces },
];

const filters: Array<{ id: PromptFilter; labelKey: Parameters<typeof t>[1] }> = [
  { id: "all", labelKey: "promptStudio.filter.all" },
  { id: "active", labelKey: "promptStudio.filter.active" },
  { id: "editable", labelKey: "promptStudio.filter.editable" },
  { id: "readonly", labelKey: "promptStudio.filter.readonly" },
  { id: "overrides", labelKey: "promptStudio.filter.overrides" },
];

const PROMPT_STUDIO_LOCALE_KEY = "rumi.promptStudio.locale";
const localeLabels: Record<LocaleSetting, string> = {
  auto: "AUTO",
  ja: "JA",
  en: "EN",
  zh: "中文",
  ko: "한국어",
  es: "ES",
  fr: "FR",
  de: "DE",
};
const promptStudioLocaleOptions: LocaleSetting[] = ["auto", ...supportedLocales];
type StudioMessage = (key: Parameters<typeof t>[1], values?: Record<string, string | number>) => string;

function searchParam(name: string): string {
  try {
    return new URLSearchParams(window.location.search).get(name) ?? "";
  } catch {
    return "";
  }
}

function storedPromptStudioLocale(fallback: LocaleSetting): LocaleSetting {
  const urlLocale = searchParam("locale");
  if (isLocaleSetting(urlLocale)) return urlLocale;
  try {
    const stored = window.localStorage.getItem(PROMPT_STUDIO_LOCALE_KEY);
    if (isLocaleSetting(stored)) return stored;
  } catch {
    // localStorage may be unavailable in tests or privacy modes.
  }
  return fallback || "auto";
}

function setUrlParam(name: string, value: string) {
  const url = new URL(window.location.href);
  if (value) url.searchParams.set(name, value);
  else url.searchParams.delete(name);
  window.history.replaceState({ ...window.history.state, [name]: value }, "", `${url.pathname}${url.search}${url.hash}`);
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

function modelProfileLabel(profile?: ModelProfile | null): string {
  if (!profile) return "";
  return String(profile.disambiguated_name || profile.display_name || profile.qualified_model_id || profile.profile_id || "").trim();
}

function modelProfileModel(profile?: ModelProfile | null): string {
  if (!profile) return "";
  return String(profile.qualified_model_id || profile.profile_id || profile.model_id || "").trim();
}

function modelProfileSubtitle(profile?: ModelProfile | null): string {
  if (!profile) return "";
  return [
    profile.provider_display_name || profile.provider_id,
    profile.model_id,
    profile.supports_tool_calling ? "tools" : "",
  ].filter(Boolean).join(" / ");
}

function tokenizerStatusText(tokenizer?: TokenizerInfo | null): string {
  if (!tokenizer) return "";
  if (tokenizer.source === "same_model_provider") return "same-model provider";
  if (tokenizer.status === "default") return "default tokenizer";
  return tokenizerLabel(tokenizer) || String(tokenizer.status || tokenizer.source || "");
}

function verdictTone(status?: string): string {
  if (status === "matched" || status === "selected" || status === "candidate") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-100";
  if (status === "idle" || status === "not-selected" || status === "none") return "border-zinc-800 bg-zinc-950/70 text-zinc-400";
  if (status === "passive") return "border-cyan-500/25 bg-cyan-500/10 text-cyan-100";
  if (status === "blocked") return "border-amber-500/25 bg-amber-500/10 text-amber-100";
  return "border-zinc-800 bg-zinc-950/70 text-zinc-300";
}

function localizedStudioVerdict(
  verdict: Record<string, string>,
  counts: { skillCount: number; selectedToolSegmentCount: number; selectedToolCount: number; candidateCount: number; templatePolicyRequested: boolean; templatePolicyBlocked: boolean },
  msg: StudioMessage,
): { title: string; detail: string } {
  const id = String(verdict.id || "");
  if (id === "skill") {
    return {
      title: msg("promptStudio.verdict.skillTitle"),
      detail: counts.skillCount > 0
        ? msg("promptStudio.verdict.skillMatched", { count: counts.skillCount })
        : msg("promptStudio.verdict.skillNone"),
    };
  }
  if (id === "tool_schema") {
    return {
      title: msg("promptStudio.verdict.toolSchemaTitle"),
      detail: counts.selectedToolSegmentCount > 0
        ? msg("promptStudio.verdict.toolSchemaSelected", { count: counts.selectedToolSegmentCount })
        : counts.selectedToolCount > 0
          ? msg("promptStudio.verdict.toolSchemaMissingActive")
          : msg("promptStudio.verdict.toolSchemaNoSelectedTool"),
    };
  }
  if (id === "prompt_tool_judgement") {
    return {
      title: msg("promptStudio.verdict.promptToToolTitle"),
      detail: counts.candidateCount > 0
        ? msg("promptStudio.verdict.promptToToolMatched", { count: counts.candidateCount })
        : msg("promptStudio.verdict.promptToToolNone"),
    };
  }
  if (id === "template_tool_policy") {
    return {
      title: msg("promptStudio.verdict.templatePolicyTitle"),
      detail: counts.templatePolicyBlocked
        ? msg("promptStudio.verdict.templatePolicyBlocked")
        : counts.templatePolicyRequested
          ? msg("promptStudio.verdict.templatePolicyResolved")
          : msg("promptStudio.verdict.templatePolicyNone"),
    };
  }
  if (id === "safety") {
    return {
      title: msg("promptStudio.verdict.safetyTitle"),
      detail: msg("promptStudio.verdict.safetyPassive"),
    };
  }
  return {
    title: String(verdict.title || msg("promptStudio.promptFallbackName")),
    detail: String(verdict.detail || ""),
  };
}

function catalogTemplateLabel(template?: TemplateCatalogMetadataItem | null): string {
  if (!template) return "";
  const metadata = recordFromUnknown(template.metadata);
  return String(metadata.title || template.label || template.id || "").trim();
}

function findCatalogTemplate(catalog: UICatalog | null, templateId: string, capability?: string): TemplateCatalogMetadataItem | null {
  const templates = catalog?.templates ?? [];
  const direct = templates.find((item) => item.id === templateId);
  if (direct) return direct;
  if (!capability) return null;
  return templates.find((item) => {
    const capabilities = recordFromUnknown(item.capabilities);
    return listFromUnknown(capabilities.provides).map(String).includes(capability);
  }) ?? null;
}

function localizedDecisionBoundary(value: unknown, msg: StudioMessage): string {
  const text = String(value || "").trim();
  if (!text || text === "Prompt text can suggest relevance, but cannot attach or execute tools.") {
    return msg("promptStudio.promptToolBoundary");
  }
  return text;
}

function ToolCandidateCard({ item, msg }: { item: Record<string, unknown>; msg: StudioMessage }) {
  const why = listFromUnknown(item.why).map(String);
  const matchedFrom = Array.isArray(item.matched_from) ? item.matched_from.join(", ") : String(item.matched_from || msg("promptStudio.matchFallback"));
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-zinc-100">{String(item.name || item.tool_id || msg("promptStudio.toolFallback"))}</div>
          <div className="mt-1 truncate font-mono text-[10px] text-zinc-600">{String(item.tool_id || "")}</div>
        </div>
        <span className="rounded border border-violet-500/25 bg-violet-500/10 px-1.5 py-0.5 font-mono text-[10px] text-violet-100">
          {Number(item.score || 0).toFixed(2)}
        </span>
      </div>
      <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-zinc-400">{String(item.summary || msg("promptStudio.noSummary"))}</p>
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
  modelProfiles,
  selectedModelProfileId,
  templateAiInputIds,
  templateToolPolicyIds,
  templatePolicySettings,
  modelSelectorTemplate,
  promptWorkspaceTemplate,
  promptCompactionTemplate,
  locale,
  busy,
  onInputChange,
  onToolsChange,
  onModelChange,
  onRun,
}: {
  result: PromptStudioTestResult | null;
  testInput: string;
  testTools: string;
  modelProfiles: ModelProfile[];
  selectedModelProfileId: string;
  templateAiInputIds: string[];
  templateToolPolicyIds: string[];
  templatePolicySettings: TemplateToolPolicySettings;
  modelSelectorTemplate: TemplateCatalogMetadataItem | null;
  promptWorkspaceTemplate: TemplateCatalogMetadataItem | null;
  promptCompactionTemplate: TemplateCatalogMetadataItem | null;
  locale: LocaleSetting;
  busy: string | null;
  onInputChange: (value: string) => void;
  onToolsChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onRun: () => void;
}) {
  const msg = (key: Parameters<typeof t>[1], values: Record<string, string | number> = {}) => t(locale, key, values);
  const verdicts = result?.verdicts ?? [];
  const matchedSkills = result?.matched_skills ?? [];
  const selectedToolSegments = result?.selected_tool_segments ?? [];
  const candidateSegments = result?.candidate_tool_segments ?? [];
  const candidates = result?.tool_candidates?.combined ?? [];
  const analysis = recordFromUnknown(result?.prompt_tool_analysis);
  const templateResolution = recordFromUnknown(result?.template_tool_policy_resolution);
  const templatePolicy = recordFromUnknown(templateResolution.policy);
  const templateDiagnostics = listFromUnknown(templateResolution.diagnostics);
  const resolvedAiInputIds = listFromUnknown(templateResolution.resolved_ai_input_ids).map(String);
  const resolvedPolicyIds = listFromUnknown(templateResolution.resolved_template_tool_policy_ids).map(String);
  const projectedPolicyIds = listFromUnknown(templateResolution.resolved_template_tool_policy_projected_ids).map(String);
  const templatePolicyRequested = Boolean(templateResolution.id_requested || templateAiInputIds.length || templateToolPolicyIds.length);
  const templatePolicyBlocked = Boolean(templateResolution.blocked || templatePolicy.template_policy_blocked);
  const segments = result?.segments ?? [];
  const selectedToolCount = splitCsvList(testTools).length;
  const selectedModelProfile = modelProfiles.find((profile) => profile.profile_id === selectedModelProfileId) ?? null;
  const focusedToolSegments = [...selectedToolSegments, ...candidateSegments].filter((segment, index, items) => (
    items.findIndex((item) => item.id === segment.id && item.status === segment.status) === index
  ));
  const localizedVerdicts: Array<Record<string, string> & { title: string; detail: string }> = verdicts.map((verdict) => ({
    ...verdict,
    ...localizedStudioVerdict(verdict, {
      skillCount: matchedSkills.length,
      selectedToolSegmentCount: selectedToolSegments.length,
      selectedToolCount,
      candidateCount: candidates.length,
      templatePolicyRequested,
      templatePolicyBlocked,
    }, msg),
  }));
  const modelTemplateLabel = catalogTemplateLabel(modelSelectorTemplate) || "rumi.model_selector.default";
  const workspaceTemplateLabel = catalogTemplateLabel(promptWorkspaceTemplate) || "rumi.prompt_workspace.default";
  const compactionTemplateLabel = catalogTemplateLabel(promptCompactionTemplate) || "rumi.backend.prompt_compaction.default";
  return (
    <div className="grid gap-3">
      <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
        <div className="grid items-start gap-3">
          <div className="min-w-0">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-600" htmlFor="prompt-studio-test-model">{msg("promptStudio.testModel")}</label>
            <select
              id="prompt-studio-test-model"
              value={selectedModelProfileId}
              onChange={(event) => onModelChange(event.target.value)}
              className="mt-2 h-9 w-full rounded-lg border border-zinc-800 bg-black/25 px-3 text-xs text-zinc-200 outline-none focus:border-zinc-600"
            >
              <option value="">{msg("promptStudio.modelFallback")}</option>
              {modelProfiles.map((profile) => (
                <option key={profile.profile_id} value={profile.profile_id}>
                  {modelProfileLabel(profile)}
                </option>
              ))}
            </select>
            <div className="mt-1 flex items-center gap-1.5 text-[10px] text-zinc-600">
              <Cpu size={11} />
              <span className="min-w-0 truncate">{selectedModelProfile ? modelProfileSubtitle(selectedModelProfile) : msg("promptStudio.modelFallback")}</span>
            </div>
            <p className="mt-2 rounded-md border border-cyan-500/15 bg-cyan-500/5 p-2 text-[11px] leading-relaxed text-cyan-100/80">{msg("promptStudio.modelBoundary")}</p>
            <div className="mt-2 grid gap-1 rounded-md border border-zinc-800 bg-black/20 p-2 text-[10px] text-zinc-500">
              <div className="flex items-center justify-between gap-2">
                <span>{msg("promptStudio.modelSelectorTemplate")}</span>
                <span className="min-w-0 truncate font-mono text-zinc-300">{modelTemplateLabel}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span>{msg("promptStudio.promptWorkspaceTemplate")}</span>
                <span className="min-w-0 truncate font-mono text-zinc-300">{workspaceTemplateLabel}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span>{msg("promptStudio.compactionCapability")}</span>
                <span className="min-w-0 truncate font-mono text-zinc-300">{compactionTemplateLabel}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span>{msg("promptStudio.templateAiInput")}</span>
                <span className="min-w-0 truncate font-mono text-zinc-300">{templateAiInputIds.join(", ") || msg("promptStudio.none")}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span>{msg("promptStudio.templateToolPolicy")}</span>
                <span className="min-w-0 truncate font-mono text-zinc-300">{templateToolPolicyIds.join(", ") || msg("promptStudio.none")}</span>
              </div>
            </div>
          </div>
          <div className="min-w-0">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-600" htmlFor="prompt-studio-test-input">{msg("promptStudio.testInput")}</label>
            <textarea
              id="prompt-studio-test-input"
              value={testInput}
              onChange={(event) => onInputChange(event.target.value)}
              className="mt-2 h-28 w-full resize-none rounded-lg border border-zinc-800 bg-black/25 p-3 text-sm leading-relaxed text-zinc-200 outline-none focus:border-zinc-600"
            />
          </div>
          <div className="min-w-0">
            <label className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-600" htmlFor="prompt-studio-test-tools">{msg("promptStudio.selectedTools")}</label>
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
            className="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-lg bg-cyan-200 px-3 text-xs font-semibold text-cyan-950 hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Play size={13} />
            {msg("promptStudio.runTest")}
          </button>
        </div>
      </section>

      {result && (
        <>
          <section className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            {localizedVerdicts.map((verdict) => (
              <div key={verdict.id || verdict.title} className={cn("rounded-lg border p-3", verdictTone(verdict.status))}>
                <div className="text-xs font-semibold">{verdict.title}</div>
                <p className="mt-1 text-[11px] leading-relaxed opacity-80">{verdict.detail}</p>
              </div>
            ))}
          </section>

          <section className="grid gap-3 xl:grid-cols-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="text-xs font-semibold text-zinc-100">{msg("promptStudio.skillMatches")}</div>
                <span className="font-mono text-[10px] text-zinc-600">{matchedSkills.length}</span>
              </div>
              <div className="grid gap-2">
                {matchedSkills.map((skill, index) => (
                  <div key={`${String(skill.id || "skill")}-${index}`} className="rounded-md border border-zinc-800 bg-black/20 p-2">
                    <div className="truncate text-xs font-semibold text-zinc-200">{String(skill.display_name || skill.id || msg("promptStudio.skillFallback"))}</div>
                    <div className="mt-1 grid gap-1 text-[11px] text-zinc-500">
                      <div className="truncate">{msg("promptStudio.triggers")}: {formatInspectorValue(skill.triggers)}</div>
                      <div className="truncate">{msg("promptStudio.tools")}: {formatInspectorValue(skill.applies_to_tools)}</div>
                    </div>
                  </div>
                ))}
                {!matchedSkills.length && <div className="rounded-md border border-dashed border-zinc-800 p-4 text-center text-xs text-zinc-500">{msg("promptStudio.noSkillMatch")}</div>}
              </div>
              {result.skill_instructions && (
                <pre className="mt-3 max-h-44 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/25 p-3 font-mono text-[12px] leading-relaxed text-zinc-300">{result.skill_instructions}</pre>
              )}
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="text-xs font-semibold text-zinc-100">{msg("promptStudio.toolDecision")}</div>
                <span className="font-mono text-[10px] text-zinc-600">{msg("promptStudio.candidates", { count: candidates.length })}</span>
              </div>
              <div className="rounded-md border border-zinc-800/80 bg-black/20 px-2 py-1.5 text-xs leading-relaxed text-zinc-300">
                {localizedDecisionBoundary(analysis.decision_boundary, msg)}
              </div>
              <div className="mt-2 grid gap-2">
                {candidates.slice(0, 5).map((candidate) => <ToolCandidateCard key={String(candidate.tool_id || candidate.name)} item={candidate} msg={msg} />)}
                {!candidates.length && <div className="rounded-md border border-dashed border-zinc-800 p-4 text-center text-xs text-zinc-500">{msg("promptStudio.noToolCandidate")}</div>}
              </div>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <div className="text-xs font-semibold text-zinc-100">{msg("promptStudio.templatePolicy")}</div>
                <span className={cn("rounded border px-1.5 py-0.5 font-mono text-[10px]", templatePolicyBlocked ? "border-amber-500/25 bg-amber-500/10 text-amber-100" : templatePolicyRequested ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-100" : "border-zinc-800 bg-black/20 text-zinc-500")}>
                  {templatePolicyBlocked ? msg("promptStudio.blocked") : templatePolicyRequested ? msg("promptStudio.applied") : msg("promptStudio.idle")}
                </span>
              </div>
              <div className="grid gap-1 text-[11px] text-zinc-500">
                <div className="flex items-center justify-between gap-2">
                  <span>{msg("promptStudio.resolvedAiInput")}</span>
                  <span className="min-w-0 truncate font-mono text-zinc-300">{resolvedAiInputIds.join(", ") || templateAiInputIds.join(", ") || msg("promptStudio.none")}</span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span>{msg("promptStudio.resolvedToolPolicy")}</span>
                  <span className="min-w-0 truncate font-mono text-zinc-300">{resolvedPolicyIds.join(", ") || templateToolPolicyIds.join(", ") || msg("promptStudio.none")}</span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span>{msg("promptStudio.projectedIds")}</span>
                  <span className="min-w-0 truncate font-mono text-zinc-300">{projectedPolicyIds.join(", ") || templatePolicySettings.projectedIds.join(", ") || msg("promptStudio.none")}</span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span>{msg("promptStudio.toolChoice")}</span>
                  <span className="min-w-0 truncate font-mono text-zinc-300">{formatInspectorValue(templatePolicy.tool_choice ?? templatePolicySettings.toolChoice ?? msg("promptStudio.none"))}</span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span>{msg("promptStudio.allowedTools")}</span>
                  <span className="min-w-0 truncate font-mono text-zinc-300">{listFromUnknown(templatePolicy.tool_allowlist).map(String).join(", ") || templatePolicySettings.allowedToolIds.join(", ") || msg("promptStudio.none")}</span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span>{msg("promptStudio.deniedTools")}</span>
                  <span className="min-w-0 truncate font-mono text-zinc-300">{listFromUnknown(templatePolicy.tool_denylist).map(String).join(", ") || templatePolicySettings.deniedToolIds.join(", ") || msg("promptStudio.none")}</span>
                </div>
              </div>
              {templateDiagnostics.length > 0 && (
                <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap rounded-md border border-zinc-800 bg-black/25 p-2 font-mono text-[10px] leading-relaxed text-zinc-400">{prettyJson(templateDiagnostics)}</pre>
              )}
            </div>
          </section>

          <section className="grid gap-2">
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-600">{msg("promptStudio.testModelInput")}</div>
              <span className="font-mono text-[10px] text-zinc-600">{msg("promptStudio.segments", { count: segments.length })}</span>
            </div>
            {focusedToolSegments.map((segment) => <PromptUsageSegmentCard key={`${segment.id}-${segment.status}-test-focus`} segment={segment} />)}
            {segments.filter((segment) => segment.kind === "skill").map((segment) => <PromptUsageSegmentCard key={`${segment.id}-${segment.status}-test-skill`} segment={segment} />)}
            {!focusedToolSegments.length && !segments.some((segment) => segment.kind === "skill") && (
              <div className="rounded-lg border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500">{msg("promptStudio.noFocusedSegment")}</div>
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

export function resolvePromptStudioSelection(result: PromptStudioData, promptId?: string): PromptStudioPrompt | null {
  const requestedPromptId = String(promptId || "").trim();
  const detailPrompt = result.selected_prompt ?? null;
  if (requestedPromptId && detailPrompt && promptKey(detailPrompt) === requestedPromptId) {
    return detailPrompt;
  }
  const requestedPrompt = requestedPromptId
    ? result.prompts.find((prompt) => promptKey(prompt) === requestedPromptId)
    : null;
  return requestedPrompt ?? detailPrompt ?? result.prompts[0] ?? null;
}

export function buildPromptRollbackPayload(
  prompt: PromptStudioPrompt | null | undefined,
  versionId: string,
  profileId?: string,
) {
  const expectedBodyHash = typeof prompt?.body_hash === "string" && prompt.body_hash.trim()
    ? prompt.body_hash
    : undefined;
  return {
    profile_id: profileId || undefined,
    prompt_id: promptKey(prompt),
    version_id: versionId,
    expected_body_hash: expectedBodyHash,
  };
}

function updateStudioUrl(profileId: string, conversationId: string, promptId: string, modelProfileId = "") {
  const url = new URL(window.location.href);
  url.pathname = "/prompts";
  for (const name of ["profile_id", "conversation_id", "prompt_id", "model_profile_id", "model"]) {
    url.searchParams.delete(name);
  }
  if (profileId) url.searchParams.set("profile_id", profileId);
  if (conversationId) url.searchParams.set("conversation_id", conversationId);
  if (promptId) url.searchParams.set("prompt_id", promptId);
  if (modelProfileId) url.searchParams.set("model_profile_id", modelProfileId);
  window.history.replaceState({ promptId }, "", `${url.pathname}${url.search}${url.hash}`);
}

export function PromptStudio({ locale = "auto" }: { locale?: LocaleSetting } = {}) {
  const initialProfileId = searchParam("profile_id");
  const initialConversationId = searchParam("conversation_id");
  const initialPromptId = searchParam("prompt_id");
  const initialModelProfileId = searchParam("model_profile_id") || searchParam("model");
  const [studioLocale, setStudioLocale] = useState<LocaleSetting>(() => storedPromptStudioLocale(locale));
  const [profileId, setProfileId] = useState(initialProfileId);
  const [conversationId] = useState(initialConversationId);
  const [selectedId, setSelectedId] = useState(initialPromptId);
  const [data, setData] = useState<PromptStudioData | null>(null);
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<PromptFilter>("all");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("selected");
  const [diffText, setDiffText] = useState("");
  const [lintResult, setLintResult] = useState<Record<string, unknown> | null>(null);
  const [compactResult, setCompactResult] = useState<Record<string, unknown> | null>(null);
  const [testInput, setTestInput] = useState("計算 QA: 12 * 8 を一文で確認して。");
  const [testTools, setTestTools] = useState("");
  const [modelProfiles, setModelProfiles] = useState<ModelProfile[]>([]);
  const [selectedModelProfileId, setSelectedModelProfileId] = useState(initialModelProfileId);
  const [uiCatalog, setUiCatalog] = useState<UICatalog | null>(null);
  const [testResult, setTestResult] = useState<PromptStudioTestResult | null>(null);
  const [busy, setBusy] = useState<string | null>("load");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const loadRequestRef = useRef(0);
  const resolvedLocale = normalizeLocale(studioLocale);
  const msg = useCallback((key: Parameters<typeof t>[1], values: Record<string, string | number> = {}) => t(studioLocale, key, values), [studioLocale]);

  const loadStudio = useCallback((promptId?: string, modelProfileId = selectedModelProfileId) => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    setBusy("load");
    void api.getPromptStudio({
      profile_id: profileId || undefined,
      conversation_id: conversationId || undefined,
      prompt_id: promptId || undefined,
      model_profile_id: modelProfileId || undefined,
      model: modelProfileId || undefined,
    })
      .then((result) => {
        if (loadRequestRef.current !== requestId) return;
        const selected = resolvePromptStudioSelection(result, promptId);
        const nextPromptId = promptKey(selected);
        setData(result);
        setProfileId(result.profile_id);
        setSelectedId(nextPromptId);
        setDraft(promptBody(selected));
        setDiffText("");
        setLintResult(selected?.lint ?? null);
        setCompactResult(null);
        setError(null);
        updateStudioUrl(result.profile_id, conversationId, nextPromptId, modelProfileId || result.model_profile_id || "");
      })
      .catch((loadError) => {
        if (loadRequestRef.current === requestId) {
          setError(loadError instanceof Error ? loadError.message : msg("promptStudio.errorLoad"));
        }
      })
      .finally(() => {
        if (loadRequestRef.current === requestId) setBusy(null);
      });
  }, [conversationId, msg, profileId, selectedModelProfileId]);

  useEffect(() => {
    loadStudio(initialPromptId);
  }, [initialPromptId, loadStudio]);

  useEffect(() => {
    let cancelled = false;
    void api.listModelProfiles()
      .then((result) => {
        if (cancelled) return;
        const profiles = [...(result.profiles ?? [])].sort((left, right) => modelProfileLabel(left).localeCompare(modelProfileLabel(right)));
        setModelProfiles(profiles);
        setSelectedModelProfileId((current) => current || profiles[0]?.profile_id || "");
      })
      .catch(() => {
        if (!cancelled) setModelProfiles([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void api.uiCatalog()
      .then((catalog) => {
        if (!cancelled) setUiCatalog(catalog);
      })
      .catch(() => {
        if (!cancelled) setUiCatalog(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
  const selectedModelProfile = useMemo(
    () => modelProfiles.find((profile) => profile.profile_id === selectedModelProfileId) ?? null,
    [modelProfiles, selectedModelProfileId],
  );
  const selectedModel = modelProfileModel(selectedModelProfile) || selectedModelProfileId;
  const selectedTokenizer = selectedPrompt?.tokenizer ?? data?.tokenizer ?? data?.active_summary?.token_estimate?.tokenizer ?? null;
  const tokenizerWarning = tokenizerWarningText(selectedTokenizer, msg("promptStudio.tokenizerFallbackWarning"));
  const showTokenizerWarning = tokenizerNeedsWarning(selectedTokenizer);
  const templateAiInput = useMemo(() => selectTemplateAiInput(uiCatalog, "chat"), [uiCatalog]);
  const templateToolPolicy = useMemo(
    () => selectTemplateToolPolicy(uiCatalog, "chat", templateAiInput),
    [templateAiInput, uiCatalog],
  );
  const templateAiInputIds = useMemo(() => templateAiInputSourceIds(templateAiInput), [templateAiInput]);
  const templateToolPolicyIds = useMemo(() => templateToolPolicySourceIds(templateToolPolicy), [templateToolPolicy]);
  const templatePolicySettings = useMemo(() => templateToolPolicySettings(templateToolPolicy), [templateToolPolicy]);
  const templatePolicyPayload = useMemo(
    () => templateToolPolicyReferencePayload(templateAiInput, templateToolPolicy),
    [templateAiInput, templateToolPolicy],
  );
  const modelSelectorTemplate = useMemo(
    () => findCatalogTemplate(uiCatalog, "rumi.model_selector.default", "rumi.model_selector"),
    [uiCatalog],
  );
  const promptWorkspaceTemplate = useMemo(
    () => findCatalogTemplate(uiCatalog, "rumi.prompt_workspace.default", "rumi.prompt_workspace"),
    [uiCatalog],
  );
  const promptCompactionTemplate = useMemo(
    () => findCatalogTemplate(uiCatalog, "rumi.backend.prompt_compaction.default", "rumi.prompt_compaction"),
    [uiCatalog],
  );

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
    setInspectorTab("selected");
    setDiffText("");
    setCompactResult(null);
    setTestResult(null);
    setNotice(null);
    updateStudioUrl(profileId, conversationId, nextId, selectedModelProfileId);
    loadStudio(nextId, selectedModelProfileId);
  };

  const runDiff = () => {
    const promptId = promptKey(selectedPrompt);
    if (!promptId) return;
    setBusy("diff");
    void api.diffPrompt({ profile_id: profileId || undefined, prompt_id: promptId, draft })
      .then((result) => {
        setDiffText(result.diff || "No changes.");
        setInspectorTab("diff");
        setError(null);
      })
      .catch((diffError) => setError(diffError instanceof Error ? diffError.message : msg("promptStudio.errorDiff")))
      .finally(() => setBusy(null));
  };

  const runLint = () => {
    setBusy("lint");
    void api.lintPrompt({ prompt: draft })
      .then((result) => {
        setLintResult(result);
        setInspectorTab("variables");
        setError(null);
      })
      .catch((lintError) => setError(lintError instanceof Error ? lintError.message : msg("promptStudio.errorLint")))
      .finally(() => setBusy(null));
  };

  const runCompact = () => {
    setBusy("compact");
    void api.compactPrompt({ prompt: draft })
      .then((result) => {
        setCompactResult(result);
        setError(null);
      })
      .catch((compactError) => setError(compactError instanceof Error ? compactError.message : msg("promptStudio.errorCompact")))
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
      model_profile_id: selectedModelProfileId || undefined,
      model: selectedModel || undefined,
      template_policy: templatePolicyPayload,
      request_context: {
        template_policy: templatePolicyPayload,
      },
    })
      .then((result) => {
        setTestResult(result);
        setInspectorTab("test");
        setError(null);
      })
      .catch((testError) => setError(testError instanceof Error ? testError.message : msg("promptStudio.errorTest")))
      .finally(() => setBusy(null));
  };

  const saveDraft = (forceOverride = false) => {
    const promptId = promptKey(selectedPrompt);
    if (!promptId) return;
    if (!canWriteDraft && !forceOverride) return;
    if (forceOverride && !canOverridePrompt && !canEditDirectly) return;
    const willWriteOverride = forceOverride || Boolean(selectedPrompt?.read_only);
    setBusy(willWriteOverride ? "override" : "save");
    const editingProfileOverride = isOverride(selectedPrompt);
    const expectedBodyHash = (!willWriteOverride || editingProfileOverride) && typeof selectedPrompt?.body_hash === "string" && selectedPrompt.body_hash.trim()
      ? selectedPrompt.body_hash
      : undefined;
    const expectedExists = willWriteOverride && !editingProfileOverride ? false : undefined;
    const request = willWriteOverride
      ? api.createPromptOverride({ profile_id: profileId || undefined, prompt_id: promptId, body: draft, expected_body_hash: expectedBodyHash, expected_exists: expectedExists, reason: "studio_override" })
      : api.savePrompt({ profile_id: profileId || undefined, prompt_id: promptId, body: draft, expected_body_hash: expectedBodyHash, reason: "studio_save" });
    void request
      .then(() => {
        setNotice(forceOverride || selectedPrompt?.read_only ? msg("promptStudio.noticeOverrideSaved") : msg("promptStudio.noticePromptSaved"));
        loadStudio(promptId);
      })
      .catch((saveError) => setError(saveError instanceof Error ? saveError.message : msg("promptStudio.errorSave")))
      .finally(() => setBusy(null));
  };

  const rollback = (versionId: string) => {
    const promptId = promptKey(selectedPrompt);
    if (!promptId || !versionId) return;
    setBusy(`rollback:${versionId}`);
    void api.rollbackPrompt(buildPromptRollbackPayload(selectedPrompt, versionId, profileId || undefined))
      .then(() => {
        setNotice(msg("promptStudio.noticeRolledBack"));
        loadStudio(promptId);
      })
      .catch((rollbackError) => setError(rollbackError instanceof Error ? rollbackError.message : msg("promptStudio.errorRollback")))
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
        setNotice(enabled ? msg("promptStudio.noticeEnabled") : msg("promptStudio.noticeDisabled"));
        loadStudio(promptKey(selectedPrompt));
      })
      .catch((toggleError) => setError(toggleError instanceof Error ? toggleError.message : msg("promptStudio.errorToggle")))
      .finally(() => setBusy(null));
  };

  const changeStudioLocale = (nextLocale: LocaleSetting) => {
    setStudioLocale(nextLocale);
    try {
      window.localStorage.setItem(PROMPT_STUDIO_LOCALE_KEY, nextLocale);
    } catch {
      // localStorage is optional for this control.
    }
    setUrlParam("locale", nextLocale);
  };

  const changeModelProfile = (nextProfileId: string) => {
    setSelectedModelProfileId(nextProfileId);
    setNotice(null);
    setUrlParam("model_profile_id", nextProfileId);
    setTestResult(null);
    loadStudio(selectedId, nextProfileId);
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
          <button type="button" onClick={goBack} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-100" aria-label={msg("promptStudio.back")}>
            <ArrowLeft size={16} />
          </button>
          <div className="flex min-w-0 items-center gap-2">
            <SlidersHorizontal size={16} className="shrink-0 text-cyan-300" />
            <h1 className="truncate text-sm font-semibold text-zinc-100">{msg("promptStudio.title")}</h1>
            <span className="hidden rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 font-mono text-[10px] text-zinc-500 sm:inline">
              {profileId || "defaultspack.startup"}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <div className="hidden h-8 max-w-[22rem] items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950 px-1.5 md:flex" aria-label={msg("promptStudio.studioModel")}>
            <Cpu size={13} className="ml-1 shrink-0 text-zinc-600" />
            <select
              value={selectedModelProfileId}
              onChange={(event) => changeModelProfile(event.target.value)}
              className="h-6 min-w-0 max-w-[15rem] rounded-md border-0 bg-transparent px-1 text-[10px] font-semibold text-zinc-300 outline-none focus:bg-zinc-900"
              title={selectedModelProfile ? modelProfileSubtitle(selectedModelProfile) : msg("promptStudio.modelFallback")}
            >
              {modelProfiles.length === 0 && <option value="">{msg("promptStudio.modelFallback")}</option>}
              {modelProfiles.map((profile) => (
                <option key={profile.profile_id} value={profile.profile_id}>
                  {modelProfileLabel(profile)}
                </option>
              ))}
            </select>
            {showTokenizerWarning ? (
              <span title={tokenizerWarning} aria-label={tokenizerWarning}>
                <AlertTriangle size={13} className="shrink-0 text-amber-300" />
              </span>
            ) : (
              <span
                className="hidden max-w-[7rem] truncate text-[10px] text-zinc-600 lg:inline"
                title={tokenizerStatusText(selectedTokenizer)}
              >
                {tokenizerStatusText(selectedTokenizer)}
              </span>
            )}
          </div>
          <div className="flex h-8 items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950 px-1.5" aria-label="Prompt Studio language">
            <Languages size={13} className="ml-1 text-zinc-600" />
            <select
              value={studioLocale}
              onChange={(event) => changeStudioLocale(event.target.value as LocaleSetting)}
              className="h-6 rounded-md border-0 bg-transparent px-1 text-[10px] font-semibold text-zinc-300 outline-none focus:bg-zinc-900"
            >
              {promptStudioLocaleOptions.map((item) => (
                <option key={item} value={item}>
                  {localeLabels[item]}{item !== "auto" && resolvedLocale === item ? " *" : ""}
                </option>
              ))}
            </select>
          </div>
          <button type="button" onClick={() => loadStudio(selectedId)} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-100" aria-label={msg("promptStudio.refresh")}>
            <RefreshCw size={15} className={cn(busy === "load" && "animate-spin")} />
          </button>
          <button type="button" onClick={runDiff} disabled={!selectedPrompt || busy === "diff" || !canWriteDraft} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-cyan-200 disabled:opacity-40" aria-label={msg("promptStudio.diff")} title={msg("promptStudio.diff")}>
            <ListFilter size={15} />
          </button>
          <button type="button" onClick={() => saveDraft(false)} disabled={!selectedPrompt || !isDirty || Boolean(busy) || !canWriteDraft} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white disabled:cursor-not-allowed disabled:opacity-45">
            <Save size={13} />
            {selectedPrompt?.read_only ? (canOverridePrompt ? msg("promptStudio.override") : msg("promptStudio.readOnly")) : msg("promptStudio.save")}
          </button>
        </div>
      </header>

      {(error || notice) && (
        <div className="shrink-0 border-b border-zinc-800/70 bg-zinc-950 px-4 py-2">
          {error && <div className="rounded-md border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-100">{error}</div>}
          {!error && notice && <div className="rounded-md border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-100">{notice}</div>}
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-[292px_minmax(0,1fr)_390px] overflow-hidden max-[1100px]:grid-cols-[260px_minmax(0,1fr)] max-[780px]:grid-cols-1">
        <aside className="flex min-h-0 flex-col border-r border-zinc-800/70 bg-zinc-950/55 max-[780px]:max-h-[34vh] max-[780px]:border-b max-[780px]:border-r-0">
          <div className="border-b border-zinc-800/70 p-3">
            <div className="relative">
              <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-600" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="h-9 w-full rounded-lg border border-zinc-800 bg-zinc-950 pl-8 pr-3 text-xs text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-zinc-600"
                placeholder={msg("promptStudio.searchPlaceholder")}
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
                  {msg(item.labelKey)}
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
                  <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-zinc-500">{prompt.description || prompt.preview || msg("promptStudio.promptFallback")}</p>
                </button>
              );
            })}
            {!prompts.length && <div className="rounded-lg border border-dashed border-zinc-800 p-4 text-center text-xs text-zinc-500">{msg("promptStudio.noPrompts")}</div>}
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
                  <span className="inline-flex items-center gap-1 rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 text-[10px] text-zinc-500">
                    {tokenText(selectedPrompt?.tokens)}
                    {showTokenizerWarning && (
                      <span title={tokenizerWarning} aria-label={tokenizerWarning}>
                        <AlertTriangle size={10} className="text-amber-300" />
                      </span>
                    )}
                  </span>
                </div>
                <p className="mt-1 truncate text-xs text-zinc-500">{selectedPrompt?.description || selectedPrompt?.source || msg("promptStudio.promptFallback")}</p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button type="button" onClick={runLint} disabled={!selectedPrompt || busy === "lint"} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-100 disabled:opacity-40" aria-label={msg("promptStudio.lint")} title={msg("promptStudio.lint")}>
                  <ShieldCheck size={15} />
                </button>
                <button type="button" onClick={runTest} disabled={!selectedPrompt || busy === "test"} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-cyan-200 disabled:opacity-40" aria-label={msg("promptStudio.runTest")} title={msg("promptStudio.runTest")}>
                  <FlaskConical size={15} />
                </button>
                <button type="button" onClick={runCompact} disabled={!selectedPrompt || busy === "compact" || !canWriteDraft} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-100 disabled:opacity-40" aria-label={msg("promptStudio.compactPrompt")} title={msg("promptStudio.compactPrompt")}>
                  <Wand2 size={15} />
                </button>
                <button type="button" onClick={() => saveDraft(true)} disabled={!selectedPrompt || Boolean(busy) || (!canOverridePrompt && !canEditDirectly)} className="rounded-md p-2 text-zinc-500 hover:bg-zinc-900 hover:text-cyan-200 disabled:opacity-40" aria-label={msg("promptStudio.createOverride")} title={msg("promptStudio.createOverride")}>
                  <SlidersHorizontal size={15} />
                </button>
              </div>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-auto p-4">
            <div className="grid min-h-full gap-3">
              {compactSuggestion && (
                <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/10 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-xs font-semibold text-cyan-100">{msg("promptStudio.compactedDraft")}</div>
                    <button type="button" onClick={() => setDraft(compactSuggestion)} className="rounded-md bg-cyan-200 px-2 py-1 text-[11px] font-semibold text-cyan-950">
                      {msg("promptStudio.apply")}
                    </button>
                  </div>
                  <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap font-mono text-[12px] leading-relaxed text-cyan-50">{compactSuggestion}</pre>
                </div>
              )}
              <label className="sr-only" htmlFor="prompt-studio-editor">{msg("promptStudio.editor")}</label>
              <textarea
                id="prompt-studio-editor"
                value={draft}
                onChange={(event) => {
                  setDraft(event.target.value);
                  setNotice(null);
                }}
                readOnly={!canWriteDraft}
                spellCheck={false}
                placeholder={busy === "load" ? msg("promptStudio.editorLoading") : msg("promptStudio.editorPlaceholder")}
                className={cn(
                  "min-h-[calc(100vh-185px)] w-full resize-none rounded-lg border border-zinc-800 bg-zinc-950/75 p-4 font-mono text-[13px] leading-relaxed text-zinc-200 outline-none focus:border-zinc-600",
                  !canWriteDraft && "cursor-default text-zinc-400 focus:border-zinc-800",
                )}
              />
            </div>
          </div>
        </main>

        <aside className="flex min-h-0 flex-col border-l border-zinc-800/70 bg-zinc-950/55 max-[1100px]:col-span-2 max-[1100px]:max-h-[46vh] max-[1100px]:border-l-0 max-[1100px]:border-t max-[780px]:col-span-1">
          <div className="flex items-center justify-between border-b border-zinc-800/70 px-4 py-3">
            <div className="text-sm font-semibold text-zinc-100">{msg("promptStudio.inspector")}</div>
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
          <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-zinc-800/70 px-3 py-2">
            {inspectorTabs.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setInspectorTab(item.id)}
                  className={cn(
                    "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border px-2 text-xs font-medium",
                    inspectorTab === item.id
                      ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-100"
                      : "border-zinc-800 bg-zinc-950/60 text-zinc-500 hover:text-zinc-200",
                  )}
                >
                  <Icon size={13} />
                  {msg(item.labelKey)}
                </button>
              );
            })}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {inspectorTab === "selected" && (
              <div className="grid gap-3">
                <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-100">
                    <Info size={13} className="text-cyan-300" />
                    {msg("promptStudio.selectedPrompt")}
                  </div>
                  <div className="space-y-1 text-[11px] text-zinc-500">
                    <div className="truncate text-sm font-semibold text-zinc-100">{selectedPrompt?.name || "Prompt"}</div>
                    <div className="break-all font-mono text-[10px] text-zinc-600">{promptKey(selectedPrompt) || "prompt"}</div>
                    <p className="leading-relaxed">{selectedPrompt?.description || selectedPrompt?.preview || msg("promptStudio.promptFallback")}</p>
                  </div>
                </section>

                <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-100">
                    <FileText size={13} className="text-cyan-300" />
                    {msg("promptStudio.source")}
                  </div>
                  <dl className="space-y-2 text-[11px]">
                    <div className="flex justify-between gap-3">
                      <dt className="text-zinc-500">{msg("promptStudio.type")}</dt>
                      <dd className="text-right text-zinc-200">{displaySource(selectedPrompt)}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-zinc-500">{msg("promptStudio.editable")}</dt>
                      <dd className="text-right text-zinc-200">{selectedPrompt?.editable ? msg("promptStudio.yes") : canOverridePrompt ? msg("promptStudio.overrideOnly") : msg("promptStudio.inspectOnly")}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-zinc-500">{msg("promptStudio.tokens")}</dt>
                      <dd className="inline-flex items-center justify-end gap-1 text-right text-zinc-200">
                        {tokenText(selectedPrompt?.tokens)}
                        {showTokenizerWarning && (
                          <span title={tokenizerWarning} aria-label={tokenizerWarning}>
                            <AlertTriangle size={11} className="text-amber-300" />
                          </span>
                        )}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-zinc-500">{msg("promptStudio.tokenizer")}</dt>
                      <dd className="min-w-0 truncate text-right text-zinc-200" title={tokenizerWarning || tokenizerStatusText(selectedTokenizer)}>
                        {tokenizerStatusText(selectedTokenizer) || msg("promptStudio.modelFallback")}
                      </dd>
                    </div>
                  </dl>
                </section>

                <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-100">
                    <ShieldCheck size={13} className="text-emerald-300" />
                    {msg("promptStudio.safetyBoundary")}
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
                        <span className={value === true ? "text-emerald-300" : "text-zinc-400"}>{value === true ? msg("promptStudio.yes") : value === false ? msg("promptStudio.no") : String(value)}</span>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-100">
                    <SlidersHorizontal size={13} className="text-cyan-300" />
                    {msg("promptStudio.activation")}
                  </div>
                  <div className="space-y-2 text-[11px] text-zinc-500">
                    <div className="flex items-center justify-between gap-2">
                      <span>{msg("promptStudio.state")}</span>
                      <span className={cn("rounded border px-1.5 py-0.5", statusBadgeClass(selectedPrompt?.activation_state))}>{selectedPrompt?.activation_state || "available"}</span>
                    </div>
                    <div className="break-all font-mono text-zinc-600">{selectedPrompt?.active_edge_id || msg("promptStudio.noActiveEdge")}</div>
                    <p className="leading-relaxed">{selectedPrompt?.active_reason || msg("promptStudio.availableInStudio")}</p>
                    {selectedPrompt?.input_role && <p className="leading-relaxed text-zinc-400">{selectedPrompt.input_role}</p>}
                    {selectedPrompt?.source_priority && <p className="leading-relaxed">{selectedPrompt.source_priority}</p>}
                  </div>
                </section>

                {(Object.keys(signalTool).length > 0 || Object.keys(signalSkill).length > 0) && (
                  <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                    <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-100">
                      <Wand2 size={13} className="text-violet-300" />
                      {msg("promptStudio.toolSkillSignal")}
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
                    {msg("promptStudio.sourceChain")}
                  </div>
                  <div className="grid gap-2">
                    {sourceChain.map((source, index) => (
                      <div key={index} className="rounded-md border border-zinc-800 bg-black/20 p-2 text-[11px] text-zinc-400">
                        <pre className="whitespace-pre-wrap break-all font-mono">{prettyJson(source)}</pre>
                      </div>
                    ))}
                    {!sourceChain.length && <div className="text-[11px] text-zinc-600">{msg("promptStudio.noSourceChain")}</div>}
                  </div>
                </section>

                <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                  <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-100">
                    <RotateCcw size={13} className="text-zinc-300" />
                    {msg("promptStudio.versions")}
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
                    {!versions.length && <div className="text-[11px] text-zinc-600">{msg("promptStudio.noVersions")}</div>}
                  </div>
                </section>
              </div>
            )}

            {inspectorTab === "test" && (
              <PromptStudioTestPanel
                result={testResult}
                testInput={testInput}
                testTools={testTools}
                modelProfiles={modelProfiles}
                selectedModelProfileId={selectedModelProfileId}
                templateAiInputIds={templateAiInputIds}
                templateToolPolicyIds={templateToolPolicyIds}
                templatePolicySettings={templatePolicySettings}
                modelSelectorTemplate={modelSelectorTemplate}
                promptWorkspaceTemplate={promptWorkspaceTemplate}
                promptCompactionTemplate={promptCompactionTemplate}
                locale={studioLocale}
                busy={busy}
                onInputChange={(value) => {
                  setTestInput(value);
                  setNotice(null);
                }}
                onToolsChange={(value) => {
                  setTestTools(value);
                  setNotice(null);
                }}
                onModelChange={changeModelProfile}
                onRun={runTest}
              />
            )}

            {inspectorTab === "diff" && (
              <pre className="min-h-[18rem] whitespace-pre-wrap rounded-lg border border-zinc-800 bg-zinc-950/75 p-4 font-mono text-[12px] leading-relaxed text-zinc-300">
                {diffText || msg("promptStudio.diffEmpty")}
              </pre>
            )}

            {inspectorTab === "usage" && (
              <div className="grid gap-3">
                <section className="grid gap-2">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-600">{msg("promptStudio.selectedPromptUsage")}</div>
                  {promptSegments.map((segment) => <PromptUsageSegmentCard key={`${segment.id}-${segment.status}-selected`} segment={segment} />)}
                  {!promptSegments.length && <div className="rounded-lg border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500">{msg("promptStudio.noRecordedUsage")}</div>}
                </section>
                <section className="grid gap-2">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-600">{msg("promptStudio.currentModelInput")}</div>
                    <span className="font-mono text-[10px] text-zinc-600">{activeSegments.length} segments</span>
                  </div>
                  {activeSegments.map((segment) => <PromptUsageSegmentCard key={`${segment.id}-${segment.status}-all`} segment={segment} />)}
                  {!activeSegments.length && <div className="rounded-lg border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500">{msg("promptStudio.noModelInputSegments")}</div>}
                </section>
              </div>
            )}

            {inspectorTab === "variables" && (
              <div className="grid gap-3">
                <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                  <h3 className="text-xs font-semibold text-zinc-100">{msg("promptStudio.variables")}</h3>
                  <pre className="mt-2 overflow-auto rounded-md bg-black/25 p-3 font-mono text-[12px] text-zinc-300">{variables.length ? prettyJson(variables) : "[]"}</pre>
                </section>
                <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                  <h3 className="text-xs font-semibold text-zinc-100">{msg("promptStudio.validation")}</h3>
                  <pre className="mt-2 overflow-auto rounded-md bg-black/25 p-3 font-mono text-[12px] text-zinc-300">{prettyJson(validation)}</pre>
                </section>
                <section className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-3">
                  <h3 className="text-xs font-semibold text-zinc-100">{msg("promptStudio.lint")}</h3>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {lintWarnings.map((warning, index) => (
                      <span key={`${String(warning)}-${index}`} className="rounded border border-amber-500/25 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-100">{String(warning)}</span>
                    ))}
                    {!lintWarnings.length && <span className="rounded border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-100">{msg("promptStudio.clean")}</span>}
                  </div>
                  <pre className="mt-2 overflow-auto rounded-md bg-black/25 p-3 font-mono text-[12px] text-zinc-300">{prettyJson(lint)}</pre>
                </section>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
