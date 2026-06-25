import type { ComposerRendererProps } from "./types";

export type ComposerExperienceVariant = "home" | "conversation";

export type ComposerTextareaMetrics = {
  minHeight: number;
  maxHeight: number;
};

export function composerTextareaMetrics(
  variant: ComposerExperienceVariant,
  viewportHeight = 900,
): ComposerTextareaMetrics {
  const safeViewportHeight = Number.isFinite(viewportHeight) && viewportHeight > 0 ? viewportHeight : 900;
  const minHeight = variant === "home" ? 52 : 44;
  const preferredMaximum = variant === "home" ? 264 : 216;
  const viewportMaximum = Math.max(132, Math.floor(safeViewportHeight * (variant === "home" ? 0.34 : 0.29)));
  return {
    minHeight,
    maxHeight: Math.max(minHeight, Math.min(preferredMaximum, viewportMaximum)),
  };
}

export function composerExperiencePlaceholder({
  isGenerating,
  isNewConversation,
  mode,
}: Pick<ComposerRendererProps, "isGenerating" | "isNewConversation" | "mode">): string {
  if (isGenerating && !isNewConversation) return "追加の指示を入力";
  if (mode === "coding") return "変更したい内容、/コマンド、@ファイル";
  if (mode === "agent") return "タスク、/コマンド、@ファイル";
  return isNewConversation
    ? "メッセージ、/コマンド、@ファイル"
    : "メッセージを入力（/ でコマンド）";
}
