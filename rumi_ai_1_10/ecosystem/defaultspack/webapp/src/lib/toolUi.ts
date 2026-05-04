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

export type SortableToolGroup = Pick<ToolGroupMeta, "id" | "label"> & {
  path?: string[];
  items?: ToolUiLike[];
};

const SUPPORTED_COMPOSER_WIDGET_KINDS = new Set<ComposerWidgetKind>(["tool_toggle", "button", "panel", "selector"]);

const TOOL_GROUP_ROOT_ORDER = [
  "browser",
  "computer",
  "coding",
  "build",
  "terminal",
  "research",
  "planning",
  "agent",
  "manage",
  "operate",
  "other",
];

const TOOL_GROUP_PATH_ORDER: Record<string, number> = {
  browser: 0,
  computer: 1,
  "coding/files/read": 10,
  "coding/files/write": 11,
  "coding/github/status": 20,
  "coding/github/commit": 21,
  "coding/terminal/exec": 30,
  build: 40,
  terminal: 50,
  research: 60,
  planning: 70,
  agent: 80,
  manage: 90,
  operate: 100,
  other: 999,
};

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

function compareText(left: string, right: string): number {
  return left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" });
}

function groupPath(group: Pick<SortableToolGroup, "id" | "path">): string[] {
  return group.path?.length ? group.path : toolGroupSegments(group.id);
}

function groupRank(group: Pick<SortableToolGroup, "id" | "path">): number {
  const path = groupPath(group);
  const normalizedPath = path.join("/");
  if (normalizedPath in TOOL_GROUP_PATH_ORDER) return TOOL_GROUP_PATH_ORDER[normalizedPath];
  const root = path[0] ?? normalizeToolGroupId(group.id);
  const rootIndex = TOOL_GROUP_ROOT_ORDER.indexOf(root);
  return rootIndex === -1 ? 500 : rootIndex * 100;
}

export function compareToolUiItems<T extends ToolUiLike>(left: T, right: T): number {
  const leftGroup = toolGroupFor(left);
  const rightGroup = toolGroupFor(right);
  return (
    compareToolGroups(leftGroup, rightGroup)
    || compareText(left.label || left.id, right.label || right.id)
    || compareText(left.id, right.id)
  );
}

export function compareToolGroups<T extends SortableToolGroup>(left: T, right: T): number {
  const leftPath = groupPath(left);
  const rightPath = groupPath(right);
  return (
    groupRank(left) - groupRank(right)
    || compareText(leftPath.join("/"), rightPath.join("/"))
    || compareText(left.label || left.id, right.label || right.id)
    || compareText(left.id, right.id)
  );
}

export function sortedToolUiItems<T extends ToolUiLike>(items: T[]): T[] {
  return [...items].sort(compareToolUiItems);
}

export function sortedToolGroups<T extends SortableToolGroup>(groups: T[]): T[] {
  return [...groups].map((group) => {
    const next = { ...group } as T;
    if (group.items) {
      (next as SortableToolGroup).items = sortedToolUiItems(group.items);
    }
    return next;
  }).sort(compareToolGroups);
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
