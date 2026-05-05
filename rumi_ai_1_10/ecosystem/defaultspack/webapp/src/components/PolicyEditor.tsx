import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Bot, Check, Cpu, RefreshCw, Save, ShieldAlert, Wrench } from "lucide-react";

import { api, type ApprovalPolicy } from "../lib/api";
import { cn } from "../lib/cn";

const DEFAULT_RISKS = ["low", "medium", "high", "critical"];

export function createDefaultApprovalPolicy(
  tools: string[] = [],
  models: string[] = [],
  risks: string[] = DEFAULT_RISKS,
): ApprovalPolicy {
  return {
    tool_policy: Object.fromEntries(tools.map((tool) => [tool, true])),
    model_policy: Object.fromEntries(models.map((model) => [model, true])),
    risk_policy: Object.fromEntries(risks.map((risk) => [risk, risk === "low"])),
    require_human_for: ["medium", "high", "critical"],
    auto_approve_low_risk: true,
  };
}

export function togglePolicyFlag(policy: ApprovalPolicy, group: "tool_policy" | "model_policy" | "risk_policy", id: string): ApprovalPolicy {
  const current = policy[group] ?? {};
  return {
    ...policy,
    [group]: {
      ...current,
      [id]: !current[id],
    },
  };
}

export function policyEnabledCount(policy: ApprovalPolicy, group: "tool_policy" | "model_policy" | "risk_policy"): number {
  return Object.values(policy[group] ?? {}).filter(Boolean).length;
}

function unique(values: string[]): string[] {
  return values.map((value) => value.trim()).filter(Boolean).filter((value, index, all) => all.indexOf(value) === index);
}

function ToggleButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex h-8 min-w-0 items-center justify-between gap-2 rounded-md border px-2 text-left text-xs transition-colors",
        active
          ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-200"
          : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300",
      )}
      title={label}
    >
      <span className="truncate">{label}</span>
      {active && <Check size={13} className="flex-shrink-0" />}
    </button>
  );
}

function PolicyGroup({
  icon,
  title,
  items,
  values,
  onToggle,
}: {
  icon: ReactNode;
  title: string;
  items: string[];
  values: Record<string, boolean>;
  onToggle: (id: string) => void;
}) {
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-950/60">
      <header className="flex items-center justify-between gap-3 border-b border-zinc-800 px-3 py-2">
        <h3 className="flex min-w-0 items-center gap-2 text-xs font-semibold text-zinc-300">
          <span className="text-zinc-500">{icon}</span>
          <span className="truncate">{title}</span>
        </h3>
        <span className="text-[10px] text-zinc-600">{Object.values(values).filter(Boolean).length}/{items.length}</span>
      </header>
      <div className="grid gap-2 p-3 sm:grid-cols-2">
        {items.map((item) => (
          <ToggleButton key={item} active={values[item] !== false} label={item} onClick={() => onToggle(item)} />
        ))}
        {items.length === 0 && <div className="text-xs text-zinc-600">No entries</div>}
      </div>
    </section>
  );
}

export function PolicyEditor({
  policy,
  toolIds = [],
  modelIds = [],
  riskLevels = DEFAULT_RISKS,
  loading = false,
  onRefresh,
  onChange,
  onSave,
}: {
  policy?: ApprovalPolicy | null;
  toolIds?: string[];
  modelIds?: string[];
  riskLevels?: string[];
  loading?: boolean;
  onRefresh?: () => void;
  onChange?: (policy: ApprovalPolicy) => void;
  onSave?: (policy: ApprovalPolicy) => Promise<void> | void;
}) {
  const allToolIds = useMemo(() => unique([...toolIds, ...Object.keys(policy?.tool_policy ?? {})]), [policy?.tool_policy, toolIds]);
  const allModelIds = useMemo(() => unique([...modelIds, ...Object.keys(policy?.model_policy ?? {})]), [modelIds, policy?.model_policy]);
  const allRiskLevels = useMemo(() => unique([...riskLevels, ...Object.keys(policy?.risk_policy ?? {})]), [policy?.risk_policy, riskLevels]);
  const [draft, setDraft] = useState<ApprovalPolicy>(() => ({
    ...createDefaultApprovalPolicy(allToolIds, allModelIds, allRiskLevels),
    ...(policy ?? {}),
  }));
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft({
      ...createDefaultApprovalPolicy(allToolIds, allModelIds, allRiskLevels),
      ...(policy ?? {}),
    });
  }, [allModelIds, allRiskLevels, allToolIds, policy]);

  const update = (next: ApprovalPolicy) => {
    setDraft(next);
    setMessage("");
    onChange?.(next);
  };

  const save = async () => {
    setSaving(true);
    setMessage("");
    try {
      if (onSave) await onSave(draft);
      else await api.updateApprovalPolicy(draft);
      setMessage("Saved");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const humanRisks = new Set(draft.require_human_for ?? []);
  const setHumanRisk = (risk: string) => {
    const next = new Set(humanRisks);
    if (next.has(risk)) next.delete(risk);
    else next.add(risk);
    update({ ...draft, require_human_for: [...next] });
  };

  return (
    <section className="flex h-full min-h-0 flex-col bg-[#09090b] text-zinc-100">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">Policy Editor</h2>
          <p className="mt-0.5 truncate text-[11px] text-zinc-500">
            {policyEnabledCount(draft, "tool_policy")} tools · {policyEnabledCount(draft, "model_policy")} models · {policyEnabledCount(draft, "risk_policy")} risks
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={loading}
              className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-900 px-2.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
              title="Refresh policy"
            >
              <RefreshCw size={14} /> Refresh
            </button>
          )}
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="flex h-8 items-center gap-1.5 rounded-md bg-zinc-100 px-2.5 text-xs font-semibold text-zinc-950 hover:bg-white disabled:opacity-50"
            title="Save policy"
          >
            <Save size={14} /> Save
          </button>
        </div>
      </header>

      {message && <div className="border-b border-zinc-800 px-4 py-2 text-xs text-zinc-400">{message}</div>}

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="grid gap-3 xl:grid-cols-3">
          <PolicyGroup
            icon={<Wrench size={15} />}
            title="Tools"
            items={allToolIds}
            values={draft.tool_policy ?? {}}
            onToggle={(id) => update(togglePolicyFlag(draft, "tool_policy", id))}
          />
          <PolicyGroup
            icon={<Cpu size={15} />}
            title="Models"
            items={allModelIds}
            values={draft.model_policy ?? {}}
            onToggle={(id) => update(togglePolicyFlag(draft, "model_policy", id))}
          />
          <PolicyGroup
            icon={<ShieldAlert size={15} />}
            title="Risk Auto-Approval"
            items={allRiskLevels}
            values={draft.risk_policy ?? {}}
            onToggle={(id) => update(togglePolicyFlag(draft, "risk_policy", id))}
          />
        </div>

        <section className="mt-3 rounded-lg border border-zinc-800 bg-zinc-950/60">
          <header className="flex items-center justify-between gap-3 border-b border-zinc-800 px-3 py-2">
            <h3 className="flex min-w-0 items-center gap-2 text-xs font-semibold text-zinc-300">
              <Bot size={15} className="text-zinc-500" />
              <span className="truncate">Human Review</span>
            </h3>
            <button
              type="button"
              onClick={() => update({ ...draft, auto_approve_low_risk: !draft.auto_approve_low_risk })}
              aria-pressed={draft.auto_approve_low_risk === true}
              className={cn(
                "h-7 rounded-md border px-2 text-[11px] font-medium",
                draft.auto_approve_low_risk
                  ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-200"
                  : "border-zinc-800 bg-zinc-900 text-zinc-500",
              )}
            >
              auto low risk
            </button>
          </header>
          <div className="grid gap-2 p-3 sm:grid-cols-4">
            {allRiskLevels.map((risk) => (
              <ToggleButton key={risk} active={humanRisks.has(risk)} label={risk} onClick={() => setHumanRisk(risk)} />
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}
