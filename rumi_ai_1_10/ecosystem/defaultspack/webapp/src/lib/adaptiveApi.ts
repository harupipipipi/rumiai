import { defaultspackApiFetch, explainDefaultspackApiError } from "./api";

type ApiErrorPayload = {
  code?: string;
  message?: string;
};

type ApiEnvelope<T> = {
  status?: "ok" | "error" | string;
  data?: T;
  error?: ApiErrorPayload;
};

export type AdaptiveTone = "neutral" | "good" | "warning" | "danger" | "info";

export type AdaptiveUseCase = {
  id: string;
  label: string;
  description: string;
  enabled: boolean;
};

export type AdaptiveRoleProfile = {
  title: string;
  scope: string;
  stakeholders: string[];
};

export type AdaptiveAutonomyLevel = "draft" | "confirm" | "supervised" | "autonomous";

export type AdaptiveAutonomyProfile = {
  level: AdaptiveAutonomyLevel;
  label: string;
  guardrails: string[];
};

export type AdaptivePermission = {
  id: string;
  label: string;
  risk: "low" | "medium" | "high" | string;
  mode: string;
  description: string;
};

export type AdaptivePackRecommendation = {
  id: string;
  label: string;
  reason: string;
  status: "recommended" | "enabled" | "needs_review" | string;
};

export type AdaptiveScenario = {
  id: string;
  label: string;
  prompt: string;
  expectedOutcome: string;
  requiredApprovals: string[];
};

export type AdaptiveSettingsDiff = {
  id: string;
  label: string;
  before: string;
  after: string;
  tone?: AdaptiveTone;
};

export type AdaptiveOnboardingState = {
  completedStepId?: string | null;
  useCases: AdaptiveUseCase[];
  role: AdaptiveRoleProfile;
  autonomy: AdaptiveAutonomyProfile;
  responsibilities: {
    owned: string[];
    excluded: string[];
  };
  review: {
    cadence: string;
    reviewers: string[];
    gates: string[];
  };
  permissions: AdaptivePermission[];
  privacyMemory: {
    memoryMode: string;
    retention: string;
    sensitiveBoundaries: string[];
  };
  skillLearning: {
    enabled: boolean;
    sources: string[];
    reviewRequired: boolean;
  };
  packRecommendations: AdaptivePackRecommendation[];
  scenarioSimulation: AdaptiveScenario[];
  settingsDiff: AdaptiveSettingsDiff[];
};

export type AdaptiveOperatingProfile = {
  id: string;
  name: string;
  summary: string;
  role: AdaptiveRoleProfile;
  autonomy: AdaptiveAutonomyProfile;
  focusAreas: string[];
  boundaries: string[];
  approvalPolicy: AdaptivePermission[];
  privacyMemory: AdaptiveOnboardingState["privacyMemory"];
  skillLearning: AdaptiveOnboardingState["skillLearning"];
  packRecommendations: AdaptivePackRecommendation[];
  review: AdaptiveOnboardingState["review"];
  updatedAt?: string | null;
};

export type AdaptiveActivityStatus = "queued" | "running" | "needs_review" | "blocked" | "done" | string;

export type AdaptiveActivityItem = {
  id: string;
  title: string;
  kind: "task" | "approval" | "memory" | "automation" | "incident" | string;
  status: AdaptiveActivityStatus;
  summary: string;
  actor: string;
  startedAt: string;
  evidenceCount: number;
  requiresReview?: boolean;
  toolLabel?: string | null;
  internalToolId?: string | null;
};

export type AdaptiveReviewQueueItem = {
  id: string;
  title: string;
  reason: string;
  risk: "low" | "medium" | "high" | string;
  requestedBy: string;
  ageLabel: string;
};

export type AdaptiveActivityState = {
  items: AdaptiveActivityItem[];
  reviewQueue: AdaptiveReviewQueueItem[];
  counters: {
    running: number;
    needsReview: number;
    blocked: number;
    completedToday: number;
  };
};

export type AdaptiveAutomationStep = {
  id: string;
  label: string;
  capabilityLabel?: string | null;
  internalToolId?: string | null;
  requiresApproval?: boolean;
};

export type AdaptiveAutomation = {
  id: string;
  name: string;
  description: string;
  trigger: string;
  schedule: string;
  enabled: boolean;
  risk: "low" | "medium" | "high" | string;
  lastRun?: string | null;
  steps: AdaptiveAutomationStep[];
};

export type AdaptiveAutomationTemplate = {
  id: string;
  name: string;
  description: string;
};

export type AdaptiveAutomationState = {
  automations: AdaptiveAutomation[];
  templates: AdaptiveAutomationTemplate[];
  simulation: {
    scenario: string;
    result: string;
    approvals: string[];
  };
};

export type AdaptiveEvidenceItem = {
  id: string;
  title: string;
  kind: "file" | "approval" | "runtime" | "memory" | "test" | string;
  sourceLabel: string;
  capturedAt: string;
  summary: string;
  confidence: number;
  redactions: string[];
  links?: Array<{ label: string; href: string }>;
  internalToolId?: string | null;
};

export type AdaptiveEvidenceBundle = {
  selectedId?: string | null;
  items: AdaptiveEvidenceItem[];
};

export type AdaptiveRepositoryPath = {
  path: string;
  role: string;
  status: "owned" | "read_only" | "external" | string;
};

export type AdaptiveRepositoryMapSection = {
  id: string;
  label: string;
  description: string;
  paths: AdaptiveRepositoryPath[];
};

export type AdaptiveRepositoryMap = {
  rootLabel: string;
  branch?: string | null;
  sections: AdaptiveRepositoryMapSection[];
  risks: string[];
};

export type AdaptiveContextBudgetSegment = {
  id: string;
  label: string;
  tokens: number;
  tone?: AdaptiveTone;
};

export type AdaptiveContextBudget = {
  used: number;
  limit: number;
  reserved: number;
  riskLevel: "low" | "medium" | "high" | string;
  lastTrim?: string | null;
  segments: AdaptiveContextBudgetSegment[];
  compressionPlan: string[];
};

function fallbackApiHeaders(method: string, headers?: HeadersInit): Headers {
  const nextHeaders = new Headers(headers);
  if (!nextHeaders.has("Content-Type")) {
    nextHeaders.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase()) && !nextHeaders.has("X-Rumi-CSRF")) {
    nextHeaders.set("X-Rumi-CSRF", `adaptive-${Date.now().toString(36)}`);
  }
  return nextHeaders;
}

function fallbackApiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  return fetch(input, {
    ...init,
    method,
    headers: fallbackApiHeaders(method, init.headers),
  });
}

function formatFallbackApiError(status: number, error?: ApiErrorPayload, statusText?: string): string {
  const label = status ? `HTTP ${status}${statusText ? ` ${statusText}` : ""}` : "adaptive API error";
  const code = error?.code ? ` (${error.code})` : "";
  const message = error?.message ? `: ${error.message}` : "";
  return `${label}${code}${message}`;
}

function adaptiveFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const fetcher = typeof defaultspackApiFetch === "function" ? defaultspackApiFetch : fallbackApiFetch;
  return fetcher(input, init);
}

function explainAdaptiveError(status: number, error?: ApiErrorPayload, statusText?: string): string {
  if (typeof explainDefaultspackApiError === "function") {
    return explainDefaultspackApiError(status, error, statusText);
  }
  return formatFallbackApiError(status, error, statusText);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function recordValue(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function isEnvelope<T>(value: unknown): value is ApiEnvelope<T> {
  return isRecord(value) && ("status" in value || "data" in value || "error" in value);
}

export async function adaptiveApiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await adaptiveFetch(path, init);
  let payload: unknown;

  try {
    payload = await response.json();
  } catch {
    if (!response.ok) {
      throw new Error(explainAdaptiveError(response.status, undefined, response.statusText));
    }
    throw new Error("adaptive API returned an invalid JSON response");
  }

  if (isEnvelope<T>(payload)) {
    if (!response.ok || payload.status === "error") {
      throw new Error(explainAdaptiveError(response.status, payload.error, response.statusText));
    }
    if ("data" in payload) return payload.data as T;
  }

  if (!response.ok) {
    throw new Error(explainAdaptiveError(response.status, undefined, response.statusText));
  }

  return payload as T;
}

export function fetchAdaptiveOnboarding(): Promise<AdaptiveOnboardingState> {
  return adaptiveApiRequest<Record<string, unknown>>("/api/onboarding/status", { cache: "no-store" })
    .then(toOnboardingState);
}

export function fetchAdaptiveOperatingProfile(): Promise<AdaptiveOperatingProfile> {
  return adaptiveApiRequest<Record<string, unknown>>("/api/onboarding/status", { cache: "no-store" })
    .then(toOperatingProfile);
}

export function saveAdaptiveOperatingProfile(profile: AdaptiveOperatingProfile): Promise<AdaptiveOperatingProfile> {
  return adaptiveApiRequest<Record<string, unknown>>(`/api/operating-profiles/${encodeURIComponent(profile.id)}/preview`, {
    method: "POST",
    body: JSON.stringify({ answers: { profile_id: profile.id, role_context: profile.role } }),
  }).then(() => profile);
}

export function fetchAdaptiveActivity(): Promise<AdaptiveActivityState> {
  return adaptiveApiRequest<Record<string, unknown>>("/api/activity-center", { cache: "no-store" })
    .then(toActivityState);
}

export function fetchAdaptiveAutomations(): Promise<AdaptiveAutomationState> {
  return adaptiveApiRequest<Record<string, unknown>>("/api/activity-center", { cache: "no-store" })
    .then(toAutomationState);
}

export function updateAdaptiveAutomation(
  automationId: string,
  patch: Partial<AdaptiveAutomation>,
): Promise<AdaptiveAutomation> {
  return adaptiveApiRequest<Record<string, unknown>>("/api/prepared-actions/prepare", {
    method: "POST",
    body: JSON.stringify({ operation: "automation.update", arguments: { automationId, patch } }),
  }).then(() => ({ id: automationId, name: String(patch.name ?? automationId), description: "", trigger: "", schedule: "", enabled: patch.enabled ?? false, risk: "medium", steps: [] }));
}

export function fetchAdaptiveEvidence(): Promise<AdaptiveEvidenceBundle> {
  return adaptiveApiRequest<Record<string, unknown>>("/api/context/evidence", {
    method: "POST",
    body: JSON.stringify({ items: [] }),
  }).then(toEvidenceBundle);
}

export function fetchAdaptiveRepositoryMap(): Promise<AdaptiveRepositoryMap> {
  return adaptiveApiRequest<Record<string, unknown>>("/api/context/repository-map", { cache: "no-store" })
    .then(toRepositoryMap);
}

export function fetchAdaptiveContextBudget(): Promise<AdaptiveContextBudget> {
  return Promise.resolve({
    used: 0,
    limit: 1,
    reserved: 0,
    riskLevel: "low",
    lastTrim: null,
    segments: [],
    compressionPlan: ["Context budget is calculated locally from bounded evidence and search results."],
  });
}

function toOnboardingState(payload: Record<string, unknown>): AdaptiveOnboardingState {
  const profile = recordValue(payload.operating_profile);
  const sideEffect = recordValue(profile.side_effect_policy ?? profile.policy);
  const uses = Array.isArray(profile.uses) ? profile.uses : [];
  const presetLabel = String(recordValue(profile.source).preset_id ?? profile.preset_id ?? "Guided");
  return {
    completedStepId: profile ? "settings-diff" : null,
    useCases: (uses.length ? uses : [{ id: "coding" }, { id: "research" }]).map((item) => {
      const record = recordValue(item);
      const id = String(record.id ?? "coding");
      return { id, label: titleCase(id), description: `${titleCase(id)} work`, enabled: true };
    }),
    role: {
      title: String(recordValue(profile.role_context).title ?? "Local operator"),
      scope: "Profile-scoped local-first runtime",
      stakeholders: ["User", "AI reviewer"],
    },
    autonomy: {
      level: "supervised",
      label: presetLabel,
      guardrails: ["External delivery still requires confirmation", "Secrets are never returned in responses", "Pack recommendations remain suggestions"],
    },
    responsibilities: {
      owned: ["Local planning", "Bounded context", "Evidence collection"],
      excluded: ["Production deploy without approval", "Raw secret access", "Purchase or payment"],
    },
    review: {
      cadence: "Review high-risk changes before commit",
      reviewers: ["User", "AI verifier"],
      gates: ["Git push", "External message", "Secret use"],
    },
    permissions: Object.entries(sideEffect).slice(0, 8).map(([id, mode]) => ({
      id,
      label: titleCase(id),
      risk: ["git_push", "external_message", "secret_use"].includes(id) ? "high" : "medium",
      mode: String(mode),
      description: "Compiled by the adaptive permission lattice.",
    })),
    privacyMemory: {
      memoryMode: String(recordValue(profile.memory_policy).mode ?? "explicit"),
      retention: "Profile-scoped retention",
      sensitiveBoundaries: ["secrets", "external sends", "cross-profile sharing"],
    },
    skillLearning: {
      enabled: Boolean(recordValue(profile.skill_learning_policy).enabled),
      sources: ["failure-to-success episodes", "verified tests", "user corrections"],
      reviewRequired: true,
    },
    packRecommendations: [],
    scenarioSimulation: [],
    settingsDiff: [],
  };
}

function toOperatingProfile(payload: Record<string, unknown>): AdaptiveOperatingProfile {
  const profile = recordValue(payload.operating_profile);
  const sideEffect = recordValue(profile.side_effect_policy ?? profile.policy);
  const presetLabel = String(recordValue(profile.source).preset_id ?? profile.preset_id ?? "guided");
  return {
    id: String(profile.profile_id ?? "default"),
    name: String(profile.operating_profile_id ?? presetLabel),
    summary: "Deterministic local-first adaptive runtime profile.",
    role: { title: String(recordValue(profile.role_context).title ?? "Local operator"), scope: "Profile-scoped", stakeholders: ["User"] },
    autonomy: { level: "supervised", label: presetLabel, guardrails: ["No occupation-based authority widening"] },
    focusAreas: (Array.isArray(profile.uses) ? profile.uses : []).map((item) => titleCase(String(recordValue(item).id ?? item))),
    boundaries: ["External messages", "Secrets", "Production deploys"],
    approvalPolicy: Object.entries(sideEffect).slice(0, 12).map(([id, mode]) => ({ id, label: titleCase(id), risk: "medium", mode: String(mode), description: "Compiled side-effect policy" })),
    privacyMemory: { memoryMode: "explicit", retention: "Profile-scoped", sensitiveBoundaries: ["secrets"] },
    skillLearning: { enabled: false, sources: ["verified episodes"], reviewRequired: true },
    packRecommendations: [],
    review: { cadence: "Before high-risk actions", reviewers: ["User"], gates: ["Exact plan"] },
    updatedAt: String(profile.updated_at ?? ""),
  };
}

function toActivityState(payload: Record<string, unknown>): AdaptiveActivityState {
  const prepared = Array.isArray(payload.prepared_actions) ? payload.prepared_actions : [];
  const conflicts = Array.isArray(payload.memory_conflicts) ? payload.memory_conflicts : [];
  const events = Array.isArray(payload.events) ? payload.events : [];
  const items: AdaptiveActivityItem[] = [
    ...prepared.map((item, index) => {
      const record = recordValue(item);
      return {
        id: String(record.id ?? `prepared-${index}`),
        title: String(record.operation ?? "Prepared action"),
        kind: "approval",
        status: String(record.status ?? "needs_review"),
        summary: "Prepared exact-plan action",
        actor: "Adaptive runtime",
        startedAt: String(record.created_at ?? ""),
        evidenceCount: Array.isArray(record.evidence_refs) ? record.evidence_refs.length : 0,
        requiresReview: true,
        toolLabel: "Prepared action",
      };
    }),
    ...events.slice(0, 6).map((item, index) => {
      const record = recordValue(item);
      return {
        id: String(record.id ?? `event-${index}`),
        title: String(record.type ?? "Adaptive event"),
        kind: "task",
        status: "done",
        summary: "Durable adaptive event",
        actor: "Runtime",
        startedAt: String(record.created_at ?? ""),
        evidenceCount: 0,
      };
    }),
  ];
  return {
    items,
    reviewQueue: conflicts.map((item, index) => {
      const record = recordValue(item);
      return { id: String(record.id ?? `conflict-${index}`), title: "Memory conflict", reason: String(record.resolution ?? "Needs review"), risk: "medium", requestedBy: "Memory", ageLabel: String(record.created_at ?? "") };
    }),
    counters: {
      running: items.filter((item) => item.status === "running").length,
      needsReview: items.filter((item) => item.status === "needs_review").length,
      blocked: items.filter((item) => item.status === "blocked").length,
      completedToday: items.filter((item) => item.status === "done").length,
    },
  };
}

function toAutomationState(_payload: Record<string, unknown>): AdaptiveAutomationState {
  return {
    automations: [],
    templates: [],
    simulation: {
      scenario: "Draft automation",
      result: "Automation remains inactive until reviewed and activated.",
      approvals: ["webhook_create", "external_message"],
    },
  };
}

function toEvidenceBundle(payload: Record<string, unknown>): AdaptiveEvidenceBundle {
  const items = Array.isArray(payload.items) ? payload.items : [];
  return {
    selectedId: null,
    items: items.map((item, index) => {
      const record = recordValue(item);
      return {
        id: String(record.path ?? `evidence-${index}`),
        title: String(record.path ?? "Evidence"),
        kind: "file",
        sourceLabel: "Bounded file read",
        capturedAt: "",
        summary: `${Array.isArray(record.lines) ? record.lines.length : 0} bounded lines`,
        confidence: 1,
        redactions: [],
      };
    }),
  };
}

function toRepositoryMap(payload: Record<string, unknown>): AdaptiveRepositoryMap {
  const files = Array.isArray(payload.files) ? payload.files.map(String) : [];
  return {
    rootLabel: String(payload.root ?? "workspace"),
    branch: null,
    sections: [{
      id: "files",
      label: "Files",
      description: "Bounded repository map",
      paths: files.slice(0, 50).map((path) => ({ path, role: "source", status: "read_only" })),
    }],
    risks: payload.truncated ? ["Repository map truncated by budget"] : [],
  };
}

function titleCase(value: string): string {
  return value.replace(/[_-]/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
