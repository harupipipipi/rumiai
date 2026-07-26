import type { ChatActivityEvent } from "../../../lib/api";
import deepThinkTemplateJson from "./templates/deepthink.json";

export type ConversationPresentationStatus = "running" | "completed" | "paused" | "failed";

export type ConversationPresentationPhase = {
  id: string;
  label: string;
  description?: string;
};

export type ConversationPresentationTemplate = {
  schemaVersion: 1;
  id: string;
  title: string;
  ariaLabel: string;
  icon: "brain-circuit" | "activity";
  tone: "violet-sky" | "neutral";
  motion: {
    entry: "rise" | "none";
    surface: "aurora" | "none";
    indicator: "orbit" | "pulse" | "none";
    activePhase: "signal" | "pulse" | "none";
  };
  event: {
    templateIdField: string;
    phaseField: string;
    phasePrefix: string;
  };
  phases: ConversationPresentationPhase[];
  dynamicPhases: {
    insertAfter: string;
    excluded: string[];
  };
  statuses: Record<ConversationPresentationStatus, string>;
  feedback: {
    reviewing?: string;
    approved?: string;
  };
};

export type ConversationPresentationView = {
  approved?: boolean;
  completedPhaseIds: Set<string>;
  events: ChatActivityEvent[];
  latestMessage: string;
  latestPhaseId: string;
  phases: ConversationPresentationPhase[];
  reviewCount: number;
  status: ConversationPresentationStatus;
  template: ConversationPresentationTemplate;
};

const ID_PATTERN = /^[A-Za-z0-9_.-]{1,96}$/;
const ALLOWED_ICONS = new Set(["brain-circuit", "activity"]);
const ALLOWED_TONES = new Set(["violet-sky", "neutral"]);
const ALLOWED_ENTRY_MOTIONS = new Set(["rise", "none"]);
const ALLOWED_SURFACE_MOTIONS = new Set(["aurora", "none"]);
const ALLOWED_INDICATOR_MOTIONS = new Set(["orbit", "pulse", "none"]);
const ALLOWED_PHASE_MOTIONS = new Set(["signal", "pulse", "none"]);
const TERMINAL_PHASES = new Set(["completed", "paused", "failed"]);

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function boundedText(value: unknown, fallback: string, maxLength = 120): string {
  const text = String(value ?? "").trim();
  return (text || fallback).slice(0, maxLength);
}

function token<T extends string>(value: unknown, allowed: Set<string>, fallback: T): T {
  const candidate = String(value ?? "");
  return (allowed.has(candidate) ? candidate : fallback) as T;
}

function phaseList(value: unknown): ConversationPresentationPhase[] {
  if (!Array.isArray(value)) return [];
  const phases: ConversationPresentationPhase[] = [];
  for (const item of value.slice(0, 24)) {
    const candidate = record(item);
    const id = String(candidate.id ?? "").trim();
    if (!ID_PATTERN.test(id) || phases.some((phase) => phase.id === id)) continue;
    phases.push({
      id,
      label: boundedText(candidate.label, id, 24),
      description: boundedText(candidate.description, "", 100) || undefined,
    });
  }
  return phases;
}

export function normalizeConversationPresentationTemplate(
  value: unknown,
  fallback: unknown = deepThinkTemplateJson,
): ConversationPresentationTemplate {
  const source = record(value);
  const safeFallback = record(fallback);
  const sourceEvent = record(source.event);
  const fallbackEvent = record(safeFallback.event);
  const sourceMotion = record(source.motion);
  const fallbackMotion = record(safeFallback.motion);
  const sourceDynamic = record(source.dynamic_phases);
  const fallbackDynamic = record(safeFallback.dynamic_phases);
  const sourceStatuses = record(source.statuses);
  const fallbackStatuses = record(safeFallback.statuses);
  const sourceFeedback = record(source.feedback);
  const fallbackFeedback = record(safeFallback.feedback);
  const phases = phaseList(source.phases);
  const fallbackPhases = phaseList(safeFallback.phases);
  const idCandidate = String(source.id ?? safeFallback.id ?? "");

  return {
    schemaVersion: 1,
    id: ID_PATTERN.test(idCandidate) ? idCandidate : "conversation.activity.v1",
    title: boundedText(source.title, boundedText(safeFallback.title, "Activity")),
    ariaLabel: boundedText(
      source.aria_label,
      boundedText(safeFallback.aria_label, "Conversation activity"),
    ),
    icon: token(
      source.icon,
      ALLOWED_ICONS,
      token(safeFallback.icon, ALLOWED_ICONS, "activity"),
    ),
    tone: token(
      source.tone,
      ALLOWED_TONES,
      token(safeFallback.tone, ALLOWED_TONES, "neutral"),
    ),
    motion: {
      entry: token(
        sourceMotion.entry,
        ALLOWED_ENTRY_MOTIONS,
        token(fallbackMotion.entry, ALLOWED_ENTRY_MOTIONS, "none"),
      ),
      surface: token(
        sourceMotion.surface,
        ALLOWED_SURFACE_MOTIONS,
        token(fallbackMotion.surface, ALLOWED_SURFACE_MOTIONS, "none"),
      ),
      indicator: token(
        sourceMotion.indicator,
        ALLOWED_INDICATOR_MOTIONS,
        token(fallbackMotion.indicator, ALLOWED_INDICATOR_MOTIONS, "none"),
      ),
      activePhase: token(
        sourceMotion.active_phase,
        ALLOWED_PHASE_MOTIONS,
        token(fallbackMotion.active_phase, ALLOWED_PHASE_MOTIONS, "none"),
      ),
    },
    event: {
      templateIdField: boundedText(
        sourceEvent.template_id_field,
        boundedText(fallbackEvent.template_id_field, "presentation_template_id"),
        64,
      ),
      phaseField: boundedText(
        sourceEvent.phase_field,
        boundedText(fallbackEvent.phase_field, "phase"),
        64,
      ),
      phasePrefix: boundedText(
        sourceEvent.phase_prefix,
        boundedText(fallbackEvent.phase_prefix, ""),
        64,
      ),
    },
    phases: phases.length > 0 ? phases : fallbackPhases,
    dynamicPhases: {
      insertAfter: boundedText(
        sourceDynamic.insert_after,
        boundedText(fallbackDynamic.insert_after, ""),
        96,
      ),
      excluded: Array.isArray(sourceDynamic.excluded)
        ? sourceDynamic.excluded.map(String).filter((id) => ID_PATTERN.test(id)).slice(0, 24)
        : Array.isArray(fallbackDynamic.excluded)
          ? fallbackDynamic.excluded.map(String).filter((id) => ID_PATTERN.test(id)).slice(0, 24)
          : [],
    },
    statuses: {
      running: boundedText(sourceStatuses.running, boundedText(fallbackStatuses.running, "Running"), 40),
      completed: boundedText(sourceStatuses.completed, boundedText(fallbackStatuses.completed, "Completed"), 40),
      paused: boundedText(sourceStatuses.paused, boundedText(fallbackStatuses.paused, "Paused"), 40),
      failed: boundedText(sourceStatuses.failed, boundedText(fallbackStatuses.failed, "Failed"), 40),
    },
    feedback: {
      reviewing: boundedText(
        sourceFeedback.reviewing,
        boundedText(fallbackFeedback.reviewing, ""),
        180,
      ) || undefined,
      approved: boundedText(
        sourceFeedback.approved,
        boundedText(fallbackFeedback.approved, ""),
        180,
      ) || undefined,
    },
  };
}

export const DEEPTHINK_PRESENTATION_TEMPLATE =
  normalizeConversationPresentationTemplate(deepThinkTemplateJson);

function eventPhase(event: ChatActivityEvent, template: ConversationPresentationTemplate): string {
  const explicit = String(event[template.event.phaseField] ?? "").trim();
  if (explicit) return explicit;
  const phase = String(event.phase ?? "");
  return template.event.phasePrefix && phase.startsWith(template.event.phasePrefix)
    ? phase.slice(template.event.phasePrefix.length)
    : phase;
}

function eventMatches(event: ChatActivityEvent, template: ConversationPresentationTemplate): boolean {
  const templateId = String(event[template.event.templateIdField] ?? "");
  if (templateId === template.id) return true;
  return Boolean(
    template.event.phasePrefix
    && String(event.phase ?? "").startsWith(template.event.phasePrefix),
  );
}

function templateForEvents(events: ChatActivityEvent[]): ConversationPresentationTemplate | null {
  const declared = events.find((event) => record(event.presentation).id);
  if (declared) {
    const template = normalizeConversationPresentationTemplate(declared.presentation);
    if (events.some((event) => eventMatches(event, template))) return template;
  }
  return events.some((event) => eventMatches(event, DEEPTHINK_PRESENTATION_TEMPLATE))
    ? DEEPTHINK_PRESENTATION_TEMPLATE
    : null;
}

export function conversationPresentationForEvents(
  allEvents: ChatActivityEvent[] | null | undefined,
): ConversationPresentationView | null {
  const sourceEvents = allEvents ?? [];
  const template = templateForEvents(sourceEvents);
  if (!template) return null;
  const events = sourceEvents.filter((event) => eventMatches(event, template));
  if (events.length === 0) return null;
  const phaseIds = events.map((event) => eventPhase(event, template));
  const latest = events.at(-1);
  const latestPhaseId = latest ? eventPhase(latest, template) : "";
  const completedPhaseIds = new Set(phaseIds);
  const baseIds = new Set(template.phases.map((phase) => phase.id));
  const excluded = new Set(template.dynamicPhases.excluded);
  const dynamicPhases: ConversationPresentationPhase[] = [];
  for (const event of events) {
    const id = eventPhase(event, template);
    if (!ID_PATTERN.test(id) || baseIds.has(id) || excluded.has(id)) continue;
    if (dynamicPhases.some((phase) => phase.id === id)) continue;
    dynamicPhases.push({
      id,
      label: boundedText(event.phase_label, id, 24),
      description: boundedText(event.phase_description, "", 100) || undefined,
    });
  }
  const insertIndex = template.phases.findIndex(
    (phase) => phase.id === template.dynamicPhases.insertAfter,
  );
  const phases = insertIndex < 0
    ? [...template.phases, ...dynamicPhases]
    : [
      ...template.phases.slice(0, insertIndex + 1),
      ...dynamicPhases,
      ...template.phases.slice(insertIndex + 1),
    ];
  const status: ConversationPresentationStatus = TERMINAL_PHASES.has(latestPhaseId)
    ? latestPhaseId as ConversationPresentationStatus
    : "running";
  const approvedEvent = [...events].reverse().find(
    (event) => typeof event.approved === "boolean",
  );

  return {
    approved: approvedEvent?.approved as boolean | undefined,
    completedPhaseIds,
    events,
    latestMessage: boundedText(
      latest?.message,
      status === "running" ? "複数段階で回答を検証しています" : template.statuses[status],
      180,
    ),
    latestPhaseId,
    phases,
    reviewCount: events.filter((event) => eventPhase(event, template) === "reviewing").length,
    status,
    template,
  };
}
