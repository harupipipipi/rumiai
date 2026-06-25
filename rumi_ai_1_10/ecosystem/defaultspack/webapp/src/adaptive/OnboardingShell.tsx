import {
  BrainCircuit,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  GraduationCap,
  KeyRound,
  PackageCheck,
  PlayCircle,
  ShieldCheck,
  SlidersHorizontal,
  UserRound,
  Workflow,
} from "lucide-react";
import { useMemo, useState } from "react";

import type { AdaptiveOnboardingState } from "../lib/adaptiveApi";
import { fetchAdaptiveOnboarding } from "../lib/adaptiveApi";
import {
  ResourceBanner,
  SurfaceHeader,
  ToneBadge,
  adaptiveControlClass,
  adaptivePageClass,
  adaptivePanelClass,
  adaptivePrimaryControlClass,
  adaptiveSectionClass,
  toneForRisk,
} from "./AdaptivePrimitives";
import { demoOnboardingState } from "./demoData";
import { useAdaptiveResource } from "./useAdaptiveResource";

const steps = [
  { id: "use-cases", label: "Use cases", icon: Workflow },
  { id: "role", label: "Role", icon: UserRound },
  { id: "autonomy", label: "Autonomy", icon: BrainCircuit },
  { id: "responsibility", label: "Responsibility", icon: ClipboardCheck },
  { id: "review", label: "Review", icon: CheckCircle2 },
  { id: "permissions", label: "Permissions", icon: KeyRound },
  { id: "privacy-memory", label: "Privacy and memory", icon: ShieldCheck },
  { id: "skill-learning", label: "Skill learning", icon: GraduationCap },
  { id: "pack-recommendations", label: "Packs", icon: PackageCheck },
  { id: "scenario-simulation", label: "Simulation", icon: PlayCircle },
  { id: "settings-diff", label: "Settings diff", icon: SlidersHorizontal },
] as const;

type StepId = (typeof steps)[number]["id"];

function StepBody({ stepId, state }: { stepId: StepId; state: AdaptiveOnboardingState }) {
  if (stepId === "use-cases") {
    return (
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {state.useCases.map((useCase) => (
          <label key={useCase.id} className="flex min-h-24 gap-3 rounded-md border border-zinc-800 bg-zinc-950/45 p-3">
            <input type="checkbox" defaultChecked={useCase.enabled} className="mt-1 h-4 w-4 accent-cyan-300" aria-label={`Enable ${useCase.label}`} />
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-zinc-100">{useCase.label}</span>
              <span className="mt-1 block text-xs leading-5 text-zinc-400">{useCase.description}</span>
            </span>
          </label>
        ))}
      </div>
    );
  }

  if (stepId === "role") {
    return (
      <div className="grid gap-3 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3">
          <p className="text-sm font-semibold text-zinc-100">{state.role.title}</p>
          <p className="mt-2 text-xs leading-5 text-zinc-400">{state.role.scope}</p>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Stakeholders</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {state.role.stakeholders.map((stakeholder) => (
              <ToneBadge key={stakeholder} tone="neutral">{stakeholder}</ToneBadge>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (stepId === "autonomy") {
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <ToneBadge tone="info">{state.autonomy.label}</ToneBadge>
          <span className="text-xs text-zinc-500">Current mode keeps actions reviewable.</span>
        </div>
        <ul className="grid gap-2 md:grid-cols-3">
          {state.autonomy.guardrails.map((guardrail) => (
            <li key={guardrail} className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3 text-xs leading-5 text-zinc-300">
              {guardrail}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (stepId === "responsibility") {
    return (
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-emerald-300">Owned</h3>
          <ul className="mt-2 space-y-2">
            {state.responsibilities.owned.map((item) => (
              <li key={item} className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3 text-xs text-zinc-300">{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-rose-300">Out of bounds</h3>
          <ul className="mt-2 space-y-2">
            {state.responsibilities.excluded.map((item) => (
              <li key={item} className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3 text-xs text-zinc-300">{item}</li>
            ))}
          </ul>
        </div>
      </div>
    );
  }

  if (stepId === "review") {
    return (
      <div className="grid gap-3 lg:grid-cols-[1fr_1fr]">
        <div className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3">
          <p className="text-sm font-semibold text-zinc-100">{state.review.cadence}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {state.review.reviewers.map((reviewer) => (
              <ToneBadge key={reviewer} tone="info">{reviewer}</ToneBadge>
            ))}
          </div>
        </div>
        <ul className="space-y-2">
          {state.review.gates.map((gate) => (
            <li key={gate} className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3 text-xs text-zinc-300">{gate}</li>
          ))}
        </ul>
      </div>
    );
  }

  if (stepId === "permissions") {
    return (
      <div className="grid gap-2 md:grid-cols-3">
        {state.permissions.map((permission) => (
          <div key={permission.id} className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3">
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-semibold text-zinc-100">{permission.label}</p>
              <ToneBadge tone={toneForRisk(permission.risk)}>{permission.risk}</ToneBadge>
            </div>
            <p className="mt-2 text-xs text-zinc-300">{permission.mode}</p>
            <p className="mt-1 text-xs leading-5 text-zinc-500">{permission.description}</p>
          </div>
        ))}
      </div>
    );
  }

  if (stepId === "privacy-memory") {
    return (
      <div className="space-y-3">
        <div className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3">
          <p className="text-sm font-semibold text-zinc-100">{state.privacyMemory.memoryMode}</p>
          <p className="mt-1 text-xs leading-5 text-zinc-400">{state.privacyMemory.retention}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {state.privacyMemory.sensitiveBoundaries.map((boundary) => (
            <ToneBadge key={boundary} tone="warning">{boundary}</ToneBadge>
          ))}
        </div>
      </div>
    );
  }

  if (stepId === "skill-learning") {
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <ToneBadge tone={state.skillLearning.enabled ? "good" : "neutral"}>{state.skillLearning.enabled ? "Enabled" : "Disabled"}</ToneBadge>
          <ToneBadge tone={state.skillLearning.reviewRequired ? "warning" : "good"}>
            {state.skillLearning.reviewRequired ? "Review required" : "Auto-apply allowed"}
          </ToneBadge>
        </div>
        <ul className="grid gap-2 md:grid-cols-3">
          {state.skillLearning.sources.map((source) => (
            <li key={source} className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3 text-xs text-zinc-300">{source}</li>
          ))}
        </ul>
      </div>
    );
  }

  if (stepId === "pack-recommendations") {
    return (
      <div className="grid gap-2 md:grid-cols-3">
        {state.packRecommendations.map((pack) => (
          <div key={pack.id} className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3">
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-semibold text-zinc-100">{pack.label}</p>
              <ToneBadge tone={toneForRisk(pack.status)}>{pack.status.replace("_", " ")}</ToneBadge>
            </div>
            <p className="mt-2 text-xs leading-5 text-zinc-400">{pack.reason}</p>
          </div>
        ))}
      </div>
    );
  }

  if (stepId === "scenario-simulation") {
    return (
      <div className="grid gap-2 lg:grid-cols-2">
        {state.scenarioSimulation.map((scenario) => (
          <div key={scenario.id} className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3">
            <p className="text-sm font-semibold text-zinc-100">{scenario.label}</p>
            <p className="mt-2 text-xs leading-5 text-zinc-300">{scenario.prompt}</p>
            <p className="mt-2 text-xs leading-5 text-zinc-500">{scenario.expectedOutcome}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {scenario.requiredApprovals.map((approval) => (
                <ToneBadge key={approval} tone="warning">{approval}</ToneBadge>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-2 md:grid-cols-3">
      {state.settingsDiff.map((diff) => (
        <div key={diff.id} className="rounded-md border border-zinc-800 bg-zinc-950/45 p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-semibold text-zinc-100">{diff.label}</p>
            <ToneBadge tone={diff.tone ?? "neutral"}>change</ToneBadge>
          </div>
          <dl className="mt-3 grid gap-2 text-xs">
            <div>
              <dt className="text-zinc-600">Before</dt>
              <dd className="mt-0.5 text-zinc-300">{diff.before}</dd>
            </div>
            <div>
              <dt className="text-zinc-600">After</dt>
              <dd className="mt-0.5 text-zinc-100">{diff.after}</dd>
            </div>
          </dl>
        </div>
      ))}
    </div>
  );
}

export function OnboardingShell({ initialState }: { initialState?: AdaptiveOnboardingState }) {
  const { data, status, error, refresh } = useAdaptiveResource({
    demoData: demoOnboardingState,
    initialData: initialState,
    load: fetchAdaptiveOnboarding,
  });
  const initialIndex = Math.max(0, steps.findIndex((step) => step.id === data.completedStepId));
  const [activeIndex, setActiveIndex] = useState(initialIndex > 0 ? initialIndex : 0);
  const activeStep = steps[activeIndex] ?? steps[0];
  const progress = useMemo(() => `${activeIndex + 1} / ${steps.length}`, [activeIndex]);

  return (
    <section className={`${adaptivePageClass} ${adaptivePanelClass}`} aria-label="Adaptive onboarding">
      <SurfaceHeader
        eyebrow="Adaptive runtime setup"
        title="Onboarding"
        description="Shape use cases, autonomy, review, privacy, skill learning, pack recommendations, and simulation before enabling runtime behavior."
        action={<ToneBadge tone="info">{progress}</ToneBadge>}
      />
      <ResourceBanner status={status} error={error} onRefresh={refresh} />

      <div className="grid min-h-[520px] lg:grid-cols-[240px_1fr]">
        <nav className="border-t border-zinc-800/70 p-2 lg:border-r lg:border-t-0" aria-label="Adaptive onboarding steps">
          <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-1">
            {steps.map((step, index) => {
              const Icon = step.icon;
              const selected = index === activeIndex;
              return (
                <button
                  key={step.id}
                  type="button"
                  onClick={() => setActiveIndex(index)}
                  aria-current={selected ? "step" : undefined}
                  className={`flex min-h-9 items-center gap-2 rounded-md px-2 text-left text-xs transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 ${
                    selected ? "bg-cyan-400/10 text-cyan-100" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100"
                  }`}
                >
                  <Icon size={14} aria-hidden="true" />
                  <span className="truncate">{step.label}</span>
                </button>
              );
            })}
          </div>
        </nav>

        <div className="min-w-0">
          <div className={adaptiveSectionClass}>
            <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Step</p>
                <h2 className="mt-1 text-sm font-semibold text-zinc-50">{activeStep.label}</h2>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  className={adaptiveControlClass}
                  onClick={() => setActiveIndex((value) => Math.max(0, value - 1))}
                  disabled={activeIndex === 0}
                  aria-label="Previous onboarding step"
                >
                  <ChevronLeft size={14} aria-hidden="true" />
                  Previous
                </button>
                <button
                  type="button"
                  className={adaptivePrimaryControlClass}
                  onClick={() => setActiveIndex((value) => Math.min(steps.length - 1, value + 1))}
                  disabled={activeIndex === steps.length - 1}
                  aria-label="Next onboarding step"
                >
                  Next
                  <ChevronRight size={14} aria-hidden="true" />
                </button>
              </div>
            </div>
            <StepBody stepId={activeStep.id} state={data} />
          </div>
        </div>
      </div>
    </section>
  );
}
