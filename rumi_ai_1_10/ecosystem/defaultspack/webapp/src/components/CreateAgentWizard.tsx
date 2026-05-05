import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Cpu,
  Globe2,
  KeyRound,
  Play,
  ShieldCheck,
  UserRound,
  Wrench,
} from "lucide-react";

import {
  api,
  type AgentRunMode,
  type AgentTemplate,
  type ApiKeySummary,
  type BrowserProfile,
  type CreateAgentRequest,
  type ModelProfile,
} from "../lib/api";
import { cn } from "../lib/cn";

export type AgentToolOption = {
  id: string;
  label: string;
  description?: string;
};

export type AgentWizardDraft = {
  template_id: string;
  name: string;
  profile_id: string;
  role: string;
  model: string;
  api_key_id: string;
  provider_id: string;
  browser_profile_id: string;
  browser_enabled: boolean;
  computer_enabled: boolean;
  tools: string[];
  run_mode: AgentRunMode;
  interval_minutes: number;
  start_now: boolean;
  stop_on_failure: boolean;
  max_cost_usd: number;
  approval_mode: "prompt" | "auto_low_risk" | "manual_only";
};

export const WIZARD_STEPS = [
  "Template",
  "Name/Profile/Role",
  "Model/API Key",
  "Browser/Computer",
  "Tools",
  "Schedule/Lifecycle",
  "Review",
] as const;

export const DEFAULT_AGENT_TEMPLATES: AgentTemplate[] = [
  {
    id: "coding",
    name: "Coding Agent",
    profile_id: "local_agent",
    role: "Implement scoped code changes, run checks, and report blockers.",
    tools: ["coding_file_read", "coding_file_write", "coding_terminal_exec", "coding_git_status"],
    lifecycle: "manual",
  },
  {
    id: "research",
    name: "Research Agent",
    profile_id: "research_agent",
    role: "Gather sources, compare claims, and produce concise findings.",
    tools: ["web_search", "reddit_search", "browser_use"],
    lifecycle: "scheduled",
  },
  {
    id: "operations",
    name: "Operations Agent",
    profile_id: "defaultspack.operations_company",
    role: "Monitor schedules, surface blockers, and coordinate follow-up work.",
    tools: ["browser_use", "computer_use", "subagent"],
    lifecycle: "non_stop",
  },
];

const DEFAULT_DRAFT: AgentWizardDraft = {
  template_id: "coding",
  name: "",
  profile_id: "local_agent",
  role: "",
  model: "",
  api_key_id: "",
  provider_id: "",
  browser_profile_id: "",
  browser_enabled: true,
  computer_enabled: false,
  tools: [],
  run_mode: "manual",
  interval_minutes: 30,
  start_now: false,
  stop_on_failure: true,
  max_cost_usd: 5,
  approval_mode: "prompt",
};

export function buildCreateAgentPayload(draft: AgentWizardDraft): CreateAgentRequest {
  const browserProfileId = draft.browser_enabled ? draft.browser_profile_id.trim() : "";
  return {
    template_id: draft.template_id || undefined,
    name: draft.name.trim(),
    profile_id: draft.profile_id.trim() || undefined,
    role: draft.role.trim() || undefined,
    model: draft.model || undefined,
    api_key_id: draft.api_key_id || null,
    provider_id: draft.provider_id || undefined,
    browser_profile_id: browserProfileId || null,
    browser_enabled: draft.browser_enabled,
    computer_enabled: draft.computer_enabled,
    tools: [...draft.tools],
    schedule: {
      enabled: draft.run_mode !== "manual",
      mode: draft.run_mode,
      interval_minutes: Math.max(1, Number(draft.interval_minutes) || 1),
      start_now: draft.start_now,
    },
    lifecycle: {
      run_mode: draft.run_mode,
      start_now: draft.start_now,
      max_cost_usd: Math.max(0, Number(draft.max_cost_usd) || 0),
      stop_on_failure: draft.stop_on_failure,
      approval_mode: draft.approval_mode,
    },
    tool_policy: {
      allowed_tools: [...draft.tools],
      browser_enabled: draft.browser_enabled,
      computer_enabled: draft.computer_enabled,
      require_approval_for: draft.approval_mode === "manual_only" ? ["low", "medium", "high"] : ["medium", "high"],
    },
  };
}

export function validateCreateAgentDraft(draft: AgentWizardDraft): string[] {
  const errors: string[] = [];
  if (!draft.name.trim()) errors.push("Agent name is required.");
  if (!draft.profile_id.trim()) errors.push("Profile is required.");
  if (!draft.role.trim()) errors.push("Role is required.");
  if (draft.run_mode !== "manual" && Math.max(1, Number(draft.interval_minutes) || 0) < 1) {
    errors.push("Interval must be at least 1 minute.");
  }
  return errors;
}

export function applyAgentTemplate(draft: AgentWizardDraft, template: AgentTemplate): AgentWizardDraft {
  return {
    ...draft,
    template_id: template.id,
    profile_id: template.profile_id ?? draft.profile_id,
    role: template.role ?? draft.role,
    model: template.model ?? draft.model,
    tools: template.tools ?? draft.tools,
    run_mode: template.lifecycle ?? draft.run_mode,
  };
}

function toggleString(items: string[], item: string): string[] {
  return items.includes(item) ? items.filter((value) => value !== item) : [...items, item];
}

function modelId(profile: ModelProfile): string {
  return profile.profile_id || profile.qualified_model_id || `${profile.provider_id}/${profile.model_id}`;
}

function browserProfileId(profile: BrowserProfile): string {
  return profile.profile_id || profile.id;
}

function apiKeyLabel(key: ApiKeySummary): string {
  return key.label || key.provider_id || key.id;
}

function SegmentedButton({
  active,
  children,
  onClick,
  title,
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={cn(
        "h-8 rounded-md border px-3 text-xs font-medium transition-colors",
        active
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
          : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200",
      )}
    >
      {children}
    </button>
  );
}

function ToggleRow({
  checked,
  icon,
  label,
  onChange,
}: {
  checked: boolean;
  icon: ReactNode;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="flex h-10 items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 text-left text-sm text-zinc-200 hover:bg-zinc-900"
      aria-pressed={checked}
    >
      <span className="flex min-w-0 items-center gap-2">
        <span className="text-zinc-500">{icon}</span>
        <span className="truncate">{label}</span>
      </span>
      <span className={cn("h-4 w-7 rounded-full p-0.5 transition-colors", checked ? "bg-emerald-500" : "bg-zinc-700")}>
        <span className={cn("block h-3 w-3 rounded-full bg-white transition-transform", checked && "translate-x-3")} />
      </span>
    </button>
  );
}

export function CreateAgentWizard({
  templates = DEFAULT_AGENT_TEMPLATES,
  modelProfiles = [],
  apiKeys = [],
  browserProfiles = [],
  tools = [],
  initialDraft,
  isBusy = false,
  onCreate,
  onCancel,
}: {
  templates?: AgentTemplate[];
  modelProfiles?: ModelProfile[];
  apiKeys?: ApiKeySummary[];
  browserProfiles?: BrowserProfile[];
  tools?: AgentToolOption[];
  initialDraft?: Partial<AgentWizardDraft>;
  isBusy?: boolean;
  onCreate?: (payload: CreateAgentRequest) => Promise<void> | void;
  onCancel?: () => void;
}) {
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<AgentWizardDraft>(() => {
    const base = { ...DEFAULT_DRAFT, ...initialDraft };
    const template = templates.find((item) => item.id === base.template_id) ?? templates[0];
    return template ? applyAgentTemplate(base, template) : base;
  });
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const errors = useMemo(() => validateCreateAgentDraft(draft), [draft]);
  const payload = useMemo(() => buildCreateAgentPayload(draft), [draft]);
  const busy = isBusy || submitting;
  const activeTemplate = templates.find((template) => template.id === draft.template_id);
  const selectedApiKey = apiKeys.find((key) => key.id === draft.api_key_id);

  const update = (patch: Partial<AgentWizardDraft>) => {
    setDraft((current) => ({ ...current, ...patch }));
    setSubmitError("");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (step < WIZARD_STEPS.length - 1) {
      setStep((current) => Math.min(WIZARD_STEPS.length - 1, current + 1));
      return;
    }
    if (errors.length) {
      setSubmitError(errors[0]);
      return;
    }
    setSubmitting(true);
    setSubmitError("");
    try {
      if (onCreate) {
        await onCreate(payload);
      } else {
        await api.createAgent(payload);
      }
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Failed to create agent.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex h-full min-h-0 flex-col border border-zinc-800 bg-[#09090b] text-zinc-100">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">Agent Factory</h2>
          <p className="mt-0.5 truncate text-[11px] text-zinc-500">{WIZARD_STEPS[step]}</p>
        </div>
        <div className="flex items-center gap-1">
          {WIZARD_STEPS.map((label, index) => (
            <button
              key={label}
              type="button"
              title={label}
              onClick={() => setStep(index)}
              className={cn(
                "h-2.5 w-7 rounded-full transition-colors",
                index === step ? "bg-emerald-400" : index < step ? "bg-zinc-500" : "bg-zinc-800",
              )}
            />
          ))}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {step === 0 && (
          <div className="grid gap-2 md:grid-cols-3">
            {templates.map((template) => (
              <button
                key={template.id}
                type="button"
                onClick={() => setDraft((current) => applyAgentTemplate(current, template))}
                className={cn(
                  "rounded-lg border p-3 text-left transition-colors",
                  draft.template_id === template.id
                    ? "border-emerald-500/40 bg-emerald-500/10"
                    : "border-zinc-800 bg-zinc-950/50 hover:bg-zinc-900",
                )}
              >
                <span className="flex items-center gap-2 text-sm font-medium text-zinc-100">
                  <Bot size={16} className="text-zinc-500" />
                  <span className="truncate">{template.name}</span>
                </span>
                <span className="mt-2 line-clamp-2 text-[11px] text-zinc-500">{template.description || template.role}</span>
                <span className="mt-3 flex flex-wrap gap-1">
                  {(template.tools ?? []).slice(0, 4).map((tool) => (
                    <span key={tool} className="rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 text-[10px] text-zinc-400">
                      {tool}
                    </span>
                  ))}
                </span>
              </button>
            ))}
          </div>
        )}

        {step === 1 && (
          <div className="grid gap-3 lg:grid-cols-[1fr_1.4fr]">
            <label className="space-y-1.5">
              <span className="flex items-center gap-1.5 text-xs font-medium text-zinc-400">
                <UserRound size={13} /> Name
              </span>
              <input
                value={draft.name}
                onChange={(event) => update({ name: event.target.value })}
                className="h-9 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                placeholder={activeTemplate?.name ?? "Agent"}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs font-medium text-zinc-400">Profile</span>
              <input
                value={draft.profile_id}
                onChange={(event) => update({ profile_id: event.target.value })}
                className="h-9 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
              />
            </label>
            <label className="space-y-1.5 lg:col-span-2">
              <span className="text-xs font-medium text-zinc-400">Role</span>
              <textarea
                value={draft.role}
                onChange={(event) => update({ role: event.target.value })}
                className="h-28 w-full resize-none rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
              />
            </label>
          </div>
        )}

        {step === 2 && (
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-xs font-medium text-zinc-400">Model</span>
              <select
                value={draft.model}
                onChange={(event) => {
                  const profile = modelProfiles.find((item) => modelId(item) === event.target.value);
                  update({ model: event.target.value, provider_id: String(profile?.provider_id ?? draft.provider_id) });
                }}
                className="h-9 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
              >
                <option value="">Default model</option>
                {modelProfiles.map((profile) => (
                  <option key={modelId(profile)} value={modelId(profile)}>
                    {profile.display_name || modelId(profile)}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="flex items-center gap-1.5 text-xs font-medium text-zinc-400">
                <KeyRound size={13} /> API Key
              </span>
              <select
                value={draft.api_key_id}
                onChange={(event) => {
                  const key = apiKeys.find((item) => item.id === event.target.value);
                  update({ api_key_id: event.target.value, provider_id: key?.provider_id ?? draft.provider_id });
                }}
                className="h-9 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
              >
                <option value="">Use provider default</option>
                {apiKeys.map((key) => (
                  <option key={key.id} value={key.id}>
                    {apiKeyLabel(key)} {key.configured ? "(saved)" : "(missing)"}
                  </option>
                ))}
              </select>
            </label>
            <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3 md:col-span-2">
              <div className="flex flex-wrap gap-2 text-[11px] text-zinc-500">
                <span>provider: {draft.provider_id || selectedApiKey?.provider_id || "default"}</span>
                <span>model: {draft.model || "default"}</span>
                <span>key: {selectedApiKey?.configured ? "saved" : "provider default"}</span>
              </div>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="grid gap-3 md:grid-cols-2">
            <ToggleRow checked={draft.browser_enabled} icon={<Globe2 size={16} />} label="Browser v2" onChange={(value) => update({ browser_enabled: value })} />
            <ToggleRow checked={draft.computer_enabled} icon={<Cpu size={16} />} label="Computer Use v2" onChange={(value) => update({ computer_enabled: value })} />
            <label className="space-y-1.5 md:col-span-2">
              <span className="text-xs font-medium text-zinc-400">Browser Profile</span>
              <select
                value={draft.browser_profile_id}
                onChange={(event) => update({ browser_profile_id: event.target.value })}
                disabled={!draft.browser_enabled}
                className="h-9 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-600 disabled:opacity-50"
              >
                <option value="">Default profile</option>
                {browserProfiles.map((profile) => (
                  <option key={browserProfileId(profile)} value={browserProfileId(profile)}>
                    {profile.label || browserProfileId(profile)} {profile.active ? "(active)" : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        {step === 4 && (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {tools.map((tool) => {
              const active = draft.tools.includes(tool.id);
              return (
                <button
                  key={tool.id}
                  type="button"
                  onClick={() => update({ tools: toggleString(draft.tools, tool.id) })}
                  className={cn(
                    "rounded-lg border p-3 text-left transition-colors",
                    active ? "border-emerald-500/40 bg-emerald-500/10" : "border-zinc-800 bg-zinc-950/50 hover:bg-zinc-900",
                  )}
                  aria-pressed={active}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-2 text-sm font-medium text-zinc-100">
                      <Wrench size={15} className="text-zinc-500" />
                      <span className="truncate">{tool.label}</span>
                    </span>
                    {active && <Check size={14} className="text-emerald-300" />}
                  </span>
                  <span className="mt-1 block truncate text-[11px] text-zinc-500">{tool.description || tool.id}</span>
                </button>
              );
            })}
            {tools.length === 0 && (
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-500">
                No tool catalog loaded.
              </div>
            )}
          </div>
        )}

        {step === 5 && (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {(["manual", "scheduled", "non_stop"] as const).map((mode) => (
                <SegmentedButton key={mode} active={draft.run_mode === mode} onClick={() => update({ run_mode: mode })} title={mode}>
                  {mode}
                </SegmentedButton>
              ))}
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <label className="space-y-1.5">
                <span className="flex items-center gap-1.5 text-xs font-medium text-zinc-400">
                  <Clock3 size={13} /> Interval
                </span>
                <input
                  type="number"
                  min={1}
                  value={draft.interval_minutes}
                  onChange={(event) => update({ interval_minutes: Number(event.target.value) })}
                  className="h-9 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                />
              </label>
              <label className="space-y-1.5">
                <span className="text-xs font-medium text-zinc-400">Max Cost USD</span>
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  value={draft.max_cost_usd}
                  onChange={(event) => update({ max_cost_usd: Number(event.target.value) })}
                  className="h-9 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                />
              </label>
              <label className="space-y-1.5">
                <span className="flex items-center gap-1.5 text-xs font-medium text-zinc-400">
                  <ShieldCheck size={13} /> Approval
                </span>
                <select
                  value={draft.approval_mode}
                  onChange={(event) => update({ approval_mode: event.target.value as AgentWizardDraft["approval_mode"] })}
                  className="h-9 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-zinc-600"
                >
                  <option value="prompt">Prompt</option>
                  <option value="auto_low_risk">Auto low risk</option>
                  <option value="manual_only">Manual only</option>
                </select>
              </label>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              <ToggleRow checked={draft.start_now} icon={<Play size={16} />} label="Start now" onChange={(value) => update({ start_now: value })} />
              <ToggleRow checked={draft.stop_on_failure} icon={<ShieldCheck size={16} />} label="Stop on failure" onChange={(value) => update({ stop_on_failure: value })} />
            </div>
          </div>
        )}

        {step === 6 && (
          <div className="grid gap-3 lg:grid-cols-2">
            {[
              ["name", payload.name],
              ["profile", payload.profile_id],
              ["role", payload.role],
              ["model", payload.model || "default"],
              ["api key", payload.api_key_id || "provider default"],
              ["browser", payload.browser_enabled ? payload.browser_profile_id || "default" : "off"],
              ["computer", payload.computer_enabled ? "on" : "off"],
              ["lifecycle", payload.lifecycle?.run_mode],
              ["tools", `${payload.tools?.length ?? 0}`],
            ].map(([label, value]) => (
              <div key={label} className="min-w-0 rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                <div className="text-[10px] uppercase text-zinc-600">{label}</div>
                <div className="mt-1 truncate text-sm text-zinc-200">{String(value ?? "")}</div>
              </div>
            ))}
            {errors.length > 0 && (
              <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-xs text-amber-200 lg:col-span-2">
                {errors[0]}
              </div>
            )}
          </div>
        )}
      </div>

      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-zinc-800 px-4 py-3">
        <div className="min-w-0 text-xs text-red-300">{submitError}</div>
        <div className="ml-auto flex items-center gap-2">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="h-8 rounded-md border border-zinc-800 bg-zinc-900 px-3 text-xs font-medium text-zinc-400 hover:bg-zinc-800"
            >
              Cancel
            </button>
          )}
          <button
            type="button"
            onClick={() => setStep((current) => Math.max(0, current - 1))}
            disabled={step === 0 || busy}
            title="Previous step"
            className="flex h-8 items-center gap-1 rounded-md border border-zinc-800 bg-zinc-900 px-3 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
          >
            <ChevronLeft size={14} /> Back
          </button>
          <button
            type="submit"
            disabled={busy}
            title={step === WIZARD_STEPS.length - 1 ? "Create agent" : "Next step"}
            className="flex h-8 items-center gap-1 rounded-md bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white disabled:opacity-50"
          >
            {step === WIZARD_STEPS.length - 1 ? "Create" : "Next"}
            {step === WIZARD_STEPS.length - 1 ? <Check size={14} /> : <ChevronRight size={14} />}
          </button>
        </div>
      </footer>
    </form>
  );
}
