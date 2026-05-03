import type { SidebarItem } from "./api";

export const COMPOSER_TOGGLE_DROP = "composer.toggle_chip";

export type ToolUiLike = Pick<SidebarItem, "id" | "label" | "description" | "tags" | "ui">;

export type ToolGroupMeta = {
  id: string;
  label: string;
  description: string;
  icon?: string;
  isDeclared: boolean;
  path: string[];
};

const SUPPORTED_COMPOSER_WIDGET_KINDS = new Set(["tool_toggle"]);

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

export function supportsComposerToggleDrop(item: ToolUiLike): boolean {
  const widgetKind = item.ui?.widget_kind;
  return Boolean(
    widgetKind
    && SUPPORTED_COMPOSER_WIDGET_KINDS.has(widgetKind)
    && item.ui?.drop_capabilities?.includes(COMPOSER_TOGGLE_DROP),
  );
}
