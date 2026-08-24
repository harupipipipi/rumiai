import { Info, X } from "lucide-react";

import type { AppMode, ContextUsageInfo } from "../renderers/types";

export type StatusCommandResultInput = {
  mode: AppMode;
  modelLabel: string;
  thinkingLevel: string | null;
  deepthinkEnabled: boolean;
  yoloMode: boolean;
  ultraYoloMode: boolean;
  selectedToolLabels: string[];
  contextUsage: ContextUsageInfo;
};

function contextUsageStatusLabel(contextUsage: ContextUsageInfo): string {
  if (contextUsage.maxContext < 0) {
    return `${contextUsage.usedTokens} tokens / unlimited`;
  }
  if (!contextUsage.maxContext) {
    return `${contextUsage.usedTokens} tokens / unknown`;
  }
  return `${contextUsage.usedTokens} / ${contextUsage.maxContext} tokens (${contextUsage.label})`;
}

/** Format the complete, human-readable result for the `/status` command. */
export function statusCommandResultMessage({
  mode,
  modelLabel,
  thinkingLevel,
  deepthinkEnabled,
  yoloMode,
  ultraYoloMode,
  selectedToolLabels,
  contextUsage,
}: StatusCommandResultInput): string {
  const visibleToolLabels = selectedToolLabels
    .map((label) => label.trim())
    .filter(Boolean);
  const toolStatus = visibleToolLabels.length
    ? `${visibleToolLabels.length} selected (${visibleToolLabels.join(", ")})`
    : "0 selected";
  return [
    "status:",
    `mode=${mode}`,
    `model=${modelLabel.trim() || "unknown"}`,
    `thinking=${thinkingLevel ?? "none"}`,
    `deepthink=${deepthinkEnabled ? "on" : "off"}`,
    `yolo=${yoloMode ? "on" : "off"}`,
    `ultra_yolo=${ultraYoloMode ? "on" : "off"}`,
    `tools=${toolStatus}`,
    `context=${contextUsageStatusLabel(contextUsage)}`,
  ].join("\n");
}

/** Render a persistent, non-error result for a frontend slash command. */
export function CommandResultNotice({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}) {
  if (!message) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-command-result-notice="status"
      className="mx-3 mt-3 rounded-2xl border border-sky-400/20 bg-sky-400/[0.08] px-4 py-3 text-zinc-100"
    >
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sky-400/15 text-sky-300"
          aria-hidden="true"
        >
          <Info size={14} strokeWidth={2.2} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">コマンド結果</p>
          <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-zinc-300">
            {message}
          </p>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-white/[0.06] hover:text-zinc-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-300"
          aria-label="ステータス結果を閉じる"
          title="閉じる"
        >
          <X size={14} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
