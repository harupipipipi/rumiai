import type { ComposerWidgetKind, SidebarItem } from "./api";

export const COMPOSER_TOGGLE_DROP = "composer.toggle_chip";
export const COMPOSER_BUTTON_DROP = "composer.action_button";
export const COMPOSER_PANEL_DROP = "composer.open_panel";
export const COMPOSER_SELECTOR_DROP = "composer.selector_chip";

export type ToolUiLike = Pick<SidebarItem, "id" | "label" | "description" | "tags" | "ui">;

export type ToolGroupMeta = {
  id: string;
  label: string;
  description: string;
  icon?: string;
  isDeclared: boolean;
  path: string[];
};

const SUPPORTED_COMPOSER_WIDGET_KINDS = new Set<ComposerWidgetKind>(["tool_toggle", "button", "panel", "selector"]);

export function normalizeToolGroupId(groupId: string): string {
  return groupId
    .trim()
    .replace(/\\/g, "/")
    .replace(/\/+/g, "/")
    .replace(/^\/|\/$/g, "");
}

export function toolGroupSegments(groupId: string): string[] {
  return normalizeToolGroupId(groupId).split("/").filter(Boolean);
}

function humanizeGroupSegment(segment: string): string {
  return segment
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function toolGroupFor(item: ToolUiLike): ToolGroupMeta {
  const groupId = normalizeToolGroupId(item.ui?.group_id ?? "");
  if (groupId) {
    const path = toolGroupSegments(groupId);
    return {
      id: groupId,
      label: item.ui?.group_label?.trim() || humanizeGroupSegment(path[path.length - 1] ?? groupId),
      description: item.description || "宣言された tool group",
      icon: item.ui?.group_icon?.trim() || undefined,
      isDeclared: true,
      path,
    };
  }

  const haystack = `${item.id} ${item.label} ${item.description ?? ""} ${(item.tags ?? []).join(" ")}`.toLowerCase();
  if (/(search|research|web|reddit|knowledge|local)/.test(haystack)) {
    return { id: "research", label: "調べる", description: "web/search/knowledge 系", icon: "search", isDeclared: false, path: ["research"] };
  }
  if (/(file|coding|code|artifact|patch|write|create|read)/.test(haystack)) {
    return { id: "build", label: "作る・編集", description: "ファイル作成、修正、読み取り", icon: "file", isDeclared: false, path: ["build"] };
  }
  if (/(browser|computer|screen|screenshot)/.test(haystack)) {
    return { id: "operate", label: "操作する", description: "browser/computer 操作", icon: "browser", isDeclared: false, path: ["operate"] };
  }
  if (/(terminal|shell|command|git)/.test(haystack)) {
    return { id: "terminal", label: "コマンド", description: "terminal/git 実行", icon: "terminal", isDeclared: false, path: ["terminal"] };
  }
  return { id: "other", label: "その他", description: "追加 tool", icon: "tool", isDeclared: false, path: ["other"] };
}

export function supportedComposerDropKind(item: ToolUiLike): ComposerWidgetKind | null {
  const widgetKind = item.ui?.widget_kind;
  if (!SUPPORTED_COMPOSER_WIDGET_KINDS.has(widgetKind as ComposerWidgetKind)) return null;

  const capabilities = item.ui?.drop_capabilities ?? [];
  if (widgetKind === "tool_toggle" && capabilities.includes(COMPOSER_TOGGLE_DROP)) return "tool_toggle";
  if (widgetKind === "button" && capabilities.includes(COMPOSER_BUTTON_DROP)) return "button";
  if (widgetKind === "panel" && capabilities.includes(COMPOSER_PANEL_DROP)) return "panel";
  if (widgetKind === "selector" && capabilities.includes(COMPOSER_SELECTOR_DROP)) return "selector";
  return null;
}

export function supportsComposerDrop(item: ToolUiLike): boolean {
  return supportedComposerDropKind(item) !== null;
}

export function supportsComposerToggleDrop(item: ToolUiLike): boolean {
  return supportedComposerDropKind(item) === "tool_toggle";
}
