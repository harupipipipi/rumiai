import type { ComposerExtensionItem } from "../renderers/types";

export type ToolMentionDetail = {
  id: string;
  name: string;
  label: string;
  description?: string;
  category?: string;
  tags?: string[];
  ui?: ComposerExtensionItem["ui"];
};

function normalizeMentionText(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/^@+/, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ");
}

export function toolMentionDisplayName(tool: ComposerExtensionItem): string {
  return (tool.label || tool.id).trim();
}

export function filterAtMentionTools(tools: ComposerExtensionItem[], query: string): ComposerExtensionItem[] {
  const normalizedQuery = normalizeMentionText(query);
  return tools
    .filter((tool) => !tool.disabled)
    .filter((tool) => {
      if (!normalizedQuery) return true;
      const haystack = [
        tool.id,
        tool.label,
        tool.description,
        ...(tool.tags ?? []),
      ].filter(Boolean).map((item) => normalizeMentionText(String(item))).join(" ");
      return haystack.includes(normalizedQuery);
    })
    .slice(0, 20);
}

export function insertToolMentionText(input: string, cursorPos: number, tool: ComposerExtensionItem): { value: string; cursor: number } {
  const textBeforeCursor = input.slice(0, cursorPos);
  const atIndex = textBeforeCursor.lastIndexOf("@");
  const insertAt = atIndex >= 0 ? atIndex : cursorPos;
  const before = input.slice(0, insertAt);
  const after = input.slice(cursorPos);
  const label = toolMentionDisplayName(tool);
  const value = `${before}@${label} ${after}`;
  return { value, cursor: insertAt + label.length + 2 };
}

export function mentionedToolDetailsFromText(text: string, tools: ComposerExtensionItem[]): ToolMentionDetail[] {
  const normalizedText = normalizeMentionText(text);
  if (!normalizedText) return [];

  const mentions: ToolMentionDetail[] = [];
  const seen = new Set<string>();
  for (const tool of tools) {
    if (tool.disabled) continue;
    const aliases = [
      tool.id,
      toolMentionDisplayName(tool),
      tool.id.replace(/_/g, " "),
      tool.id.replace(/-/g, " "),
    ].map(normalizeMentionText).filter(Boolean);
    if (!aliases.some((alias) => normalizedText.includes(alias))) continue;
    if (seen.has(tool.id)) continue;
    seen.add(tool.id);
    mentions.push({
      id: tool.id,
      name: tool.id,
      label: toolMentionDisplayName(tool),
      description: tool.description,
      category: tool.category,
      tags: tool.tags,
      ui: tool.ui,
    });
  }
  return mentions;
}
