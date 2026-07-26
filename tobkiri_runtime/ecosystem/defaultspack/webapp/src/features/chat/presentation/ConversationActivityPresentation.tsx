import { Activity, BrainCircuit, Check, Circle, Pause, TriangleAlert } from "lucide-react";
import type { CSSProperties } from "react";

import { cn } from "../../../lib/cn";
import type { ChatActivityEvent } from "../../../lib/api";
import { conversationPresentationForEvents } from "./conversationPresentation";

type ConversationActivityPresentationProps = {
  events?: ChatActivityEvent[] | null;
};

function StatusIcon({ status }: { status: "running" | "completed" | "paused" | "failed" }) {
  if (status === "completed") return <Check size={12} aria-hidden="true" />;
  if (status === "paused") return <Pause size={12} aria-hidden="true" />;
  if (status === "failed") return <TriangleAlert size={12} aria-hidden="true" />;
  return <Circle size={8} fill="currentColor" aria-hidden="true" />;
}

export function ConversationActivityPresentation({
  events,
}: ConversationActivityPresentationProps) {
  const view = conversationPresentationForEvents(events);
  if (!view) return null;
  const { template } = view;
  const completedCount = view.phases.filter((phase) => (
    view.completedPhaseIds.has(phase.id)
  )).length;
  const Icon = template.icon === "brain-circuit" ? BrainCircuit : Activity;

  return (
    <section
      className="rumi-conversation-presentation mb-3 w-full max-w-[680px]"
      aria-label={template.ariaLabel}
      aria-live="polite"
      data-motion-active={view.status === "running" ? "true" : "false"}
      data-motion-entry={template.motion.entry}
      data-motion-indicator={template.motion.indicator}
      data-motion-phase={template.motion.activePhase}
      data-motion-surface={template.motion.surface}
      data-presentation-id={template.id}
      data-presentation-status={view.status}
      data-presentation-tone={template.tone}
    >
      <div className="rumi-conversation-presentation__glow" aria-hidden="true" />
      <header className="rumi-conversation-presentation__header">
        <span className="rumi-conversation-presentation__indicator">
          <Icon size={16} aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="rumi-conversation-presentation__eyebrow">
            {template.title}
          </span>
          <span className="rumi-conversation-presentation__message">
            {view.latestMessage}
          </span>
        </span>
        <span
          className="rumi-conversation-presentation__status"
          data-status={view.status}
        >
          <StatusIcon status={view.status} />
          {template.statuses[view.status]}
        </span>
      </header>

      <div className="rumi-conversation-presentation__summary" aria-hidden="true">
        <span>{completedCount} / {view.phases.length} phases</span>
        {view.reviewCount > 0 && <span>Review {view.reviewCount}</span>}
      </div>

      <ol className="rumi-conversation-presentation__phases" aria-label={`${template.title} phases`}>
        {view.phases.map((phase, index) => {
          const completed = view.completedPhaseIds.has(phase.id);
          const active = view.latestPhaseId === phase.id;
          return (
            <li
              key={phase.id}
              className={cn(
                "rumi-conversation-presentation__phase",
                completed && "is-completed",
                active && "is-active",
              )}
              aria-current={active ? "step" : undefined}
              title={phase.description}
            >
              <span className="rumi-conversation-presentation__phase-track">
                <span
                  className="rumi-conversation-presentation__phase-fill"
                  style={{ "--rumi-phase-delay": `${index * 34}ms` } as CSSProperties}
                />
              </span>
              <span className="rumi-conversation-presentation__phase-label">
                {phase.label}
              </span>
            </li>
          );
        })}
      </ol>

      {view.approved === false && view.latestPhaseId === "reviewing" && template.feedback.reviewing && (
        <p className="rumi-conversation-presentation__feedback" data-tone="warning">
          {template.feedback.reviewing}
        </p>
      )}
      {view.approved === true && view.status === "completed" && template.feedback.approved && (
        <p className="rumi-conversation-presentation__feedback" data-tone="success">
          {template.feedback.approved}
        </p>
      )}
    </section>
  );
}
