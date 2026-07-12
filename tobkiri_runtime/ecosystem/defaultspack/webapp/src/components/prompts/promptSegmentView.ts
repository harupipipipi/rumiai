import type { PromptUsageSegment, PromptUsageSummary, TokenizerInfo } from "../../lib/api";

export type PromptSegmentSignal = {
  kind: "tool" | "skill";
  label: string;
  text: string;
};

export function allPromptUsageSegments(summary?: PromptUsageSummary | null): PromptUsageSegment[] {
  if (!summary) return [];
  return summary.segments ?? [...(summary.active_segments ?? []), ...(summary.disabled_segments ?? [])];
}

function segmentRank(segment: PromptUsageSegment): number {
  if (segment.status === "disabled") return 0;
  if (segment.status === "gated") return 1;
  if (segment.status === "budget-dropped") return 2;
  if (segment.status === "active") return 4;
  return 3;
}

export function orderPromptCommandSegments(segments: PromptUsageSegment[]): PromptUsageSegment[] {
  return [...segments].sort((a, b) => segmentRank(a) - segmentRank(b));
}

export function tokenText(value: unknown): string {
  const n = Number(value ?? 0);
  return Number.isFinite(n) && n > 0 ? `${n.toLocaleString()} tokens` : "0 tokens";
}

export function tokenizerNeedsWarning(tokenizer?: TokenizerInfo | null): boolean {
  if (!tokenizer) return false;
  return tokenizer.fallback === true || tokenizer.available === false || tokenizer.status === "default";
}

export function tokenizerWarningText(
  tokenizer?: TokenizerInfo | null,
  fallback = "Model tokenizer was not found, so the default tokenizer is being used. Counts may be significantly off.",
): string {
  if (!tokenizerNeedsWarning(tokenizer)) return "";
  return String(fallback || tokenizer?.warning || "");
}

export function tokenizerLabel(tokenizer?: TokenizerInfo | null): string {
  if (!tokenizer) return "";
  if (tokenizer.source === "same_model_provider") {
    return `borrowed: ${tokenizer.tokenizer_profile_id || tokenizer.tokenizer_model || tokenizer.tokenizer_id || "same model"}`;
  }
  if (tokenizer.source === "profile" || tokenizer.source === "profile_reference") {
    return tokenizer.tokenizer_id || tokenizer.tokenizer_profile_id || "profile tokenizer";
  }
  return tokenizer.tokenizer_id || "default tokenizer";
}

export function statusTextClass(status: string | undefined): string {
  if (status === "active") return "text-emerald-300";
  if (status === "disabled" || status === "budget-dropped") return "text-amber-300";
  if (status === "gated") return "text-sky-300";
  return "text-zinc-400";
}

export function statusBadgeClass(status: string | undefined): string {
  if (status === "active") return "border-emerald-500/25 bg-emerald-500/10 text-emerald-200";
  if (status === "budget-dropped") return "border-amber-500/25 bg-amber-500/10 text-amber-200";
  if (status === "gated") return "border-sky-500/25 bg-sky-500/10 text-sky-200";
  return "border-zinc-700 bg-zinc-900/60 text-zinc-300";
}

export function promptSegmentKindLabel(segment: PromptUsageSegment): string {
  return String(segment.kind || segment.source_type || "prompt").replace(/_/g, " ");
}

export function promptSegmentTitle(segment: PromptUsageSegment): string {
  return String(segment.label || segment.prompt_id || segment.id || "Prompt segment");
}

export function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function stringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  if (typeof value === "string") return value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
  return [];
}

export function compactText(value: unknown, fallback = "", limit = 180): string {
  const text = String(value ?? fallback).trim();
  return text.length > limit ? `${text.slice(0, limit - 3)}...` : text;
}

export function safetySummary(segment: PromptUsageSegment): string {
  const safety = recordFromUnknown(segment.safety_boundary);
  return compactText(safety.summary, "Passive text only: cannot grant permissions, call tools, or mutate chat state.");
}

export function activationLine(segment: PromptUsageSegment): string {
  const detail = recordFromUnknown(segment.activation_detail);
  return compactText(detail.effect || segment.input_role || "model input segment");
}

export function sourceLine(segment: PromptUsageSegment): string {
  const detail = recordFromUnknown(segment.activation_detail);
  return compactText(detail.trigger || segment.source_priority || segment.source || segment.source_type || "profile selection");
}

export function promptSegmentSignal(segment: PromptUsageSegment): PromptSegmentSignal | null {
  const tool = recordFromUnknown(segment.tool_signal);
  if (Object.keys(tool).length > 0) {
    const skills = stringList(tool.skills);
    const skillSuffix = skills.length ? ` Skill hints: ${skills.slice(0, 3).join(", ")}.` : "";
    return {
      kind: "tool",
      label: "Tool signal",
      text: compactText(`${tool.display_name || tool.tool_name || tool.tool_id || "Tool"} is visible as schema metadata only.${skillSuffix}`),
    };
  }
  const skill = recordFromUnknown(segment.skill_signal);
  if (Object.keys(skill).length > 0) {
    return {
      kind: "skill",
      label: "Skill trigger",
      text: compactText(skill.triggered_by || "Runtime skill matched this turn."),
    };
  }
  return null;
}
