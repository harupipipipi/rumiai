import type { ComposerWidgetAction, ComposerWidgetKind } from "./api";
import type { ComposerExtensionItem, ComposerSkillItem, DroppedWidget } from "../renderers/types";
import { supportedComposerDropKind, supportsComposerToggleDrop } from "./toolUi";

export type ComposerDropAction =
  | { type: "select_model"; profileId: string }
  | { type: "drop_widget"; widget: DroppedWidget }
  | { type: "ignore" };

const COMPOSER_ENDPOINT_ACTION_ALLOWLIST = new Set(["GET /api/coding/git/status"]);

function composerWidgetTypeForKind(kind: ComposerWidgetKind): DroppedWidget["type"] {
  return kind === "tool_toggle" ? "tool" : kind;
}

function trustedComposerWidgetFromItem(item: ComposerExtensionItem, kind: ComposerWidgetKind, enabled = true): DroppedWidget {
  const label = item.ui?.composer_label ?? item.label ?? item.id;
  const description = item.ui?.composer_description ?? item.description;
  return {
    id: item.id,
    type: composerWidgetTypeForKind(kind),
    label,
    enabled,
    widgetKind: kind,
    action: item.ui?.composer_action,
    sourceItemId: item.id,
    description,
    icon: item.ui?.composer_icon ?? item.ui?.item_icon ?? item.ui?.group_icon,
    metadata: {
      source: "composer_catalog_drop",
      tool: {
        id: item.id,
        label,
        category: item.category ?? null,
        description: description ?? null,
        tags: item.tags ?? [],
        ui: item.ui ?? null,
      },
    },
  };
}

export function trustedComposerActionForWidget(widget: DroppedWidget, toolItems: ComposerExtensionItem[]): ComposerWidgetAction | undefined {
  const itemId = widget.sourceItemId || widget.id;
  const item = toolItems.find((candidate) => candidate.id === itemId);
  const supportedKind = item ? supportedComposerDropKind(item) : null;
  if (!item || !supportedKind || supportedKind !== widget.widgetKind) return undefined;
  return item.ui?.composer_action;
}

(trustedComposerActionForWidget as typeof trustedComposerActionForWidget & {
  __rumiBundleHardeningMarker?: string;
}).__rumiBundleHardeningMarker = "trustedComposerActionForWidget";

export function resolveComposerWidgetDrop(widget: DroppedWidget, toolItems: ComposerExtensionItem[]): ComposerDropAction {
  if (widget.type === "model") return { type: "select_model", profileId: widget.id };

  const itemId = widget.sourceItemId || widget.id;
  const item = toolItems.find((candidate) => candidate.id === itemId);
  if (!item) return { type: "ignore" };

  if (widget.widgetKind === "tool_toggle" || widget.type === "tool") {
    if (!supportsComposerToggleDrop(item)) return { type: "ignore" };
    return { type: "drop_widget", widget: trustedComposerWidgetFromItem(item, "tool_toggle", widget.enabled !== false) };
  }

  const supportedKind = supportedComposerDropKind(item);
  if (widget.widgetKind && supportedKind === widget.widgetKind) {
    return { type: "drop_widget", widget: trustedComposerWidgetFromItem(item, supportedKind, widget.enabled !== false) };
  }

  return { type: "ignore" };
}

function composerToolSearchText(item: ComposerExtensionItem): string {
  const uiText = (() => {
    if (!item.ui || typeof item.ui !== "object") return "";
    try {
      return JSON.stringify(item.ui);
    } catch {
      return "";
    }
  })();
  return [
    item.id,
    item.label,
    item.description,
    item.ui?.composer_label,
    item.ui?.composer_description,
    uiText,
    ...(item.tags ?? []),
  ].filter(Boolean).join(" ").toLowerCase();
}

export function filterComposerToolMentions(items: ComposerExtensionItem[], query: string, limit = 20): ComposerExtensionItem[] {
  const q = query.trim().toLowerCase();
  const candidates = items.filter((item) => !item.disabled);
  if (!q) return candidates.slice(0, limit);
  return candidates.filter((item) => composerToolSearchText(item).includes(q)).slice(0, limit);
}

export function composerToolMentionDisplay(item: ComposerExtensionItem): { label: string; description?: string } {
  const label = item.ui?.composer_label ?? item.label ?? item.id;
  const description = item.ui?.composer_description ?? item.description;
  const details = [item.id, description && description !== label ? description : undefined].filter(Boolean).join(" - ");
  return { label, description: details || undefined };
}

export function composerToolMentionWidget(item: ComposerExtensionItem): DroppedWidget {
  const label = item.ui?.composer_label ?? item.label ?? item.id;
  const description = item.ui?.composer_description ?? item.description;
  return {
    id: item.id,
    type: "tool",
    label,
    enabled: true,
    widgetKind: "tool_toggle",
    action: item.ui?.composer_action,
    sourceItemId: item.id,
    description,
    icon: item.ui?.composer_icon ?? item.ui?.item_icon ?? item.ui?.group_icon,
    metadata: {
      source: "composer_at_mention",
      mention: {
        syntax: `@${item.id}`,
        tool_id: item.id,
      },
      tool: {
        id: item.id,
        label,
        category: item.category ?? null,
        description: description ?? null,
        tags: item.tags ?? [],
        ui: item.ui ?? null,
      },
    },
  };
}

function composerSkillSearchText(item: ComposerSkillItem): string {
  return [
    item.id,
    item.label,
    item.description,
    ...(item.triggers ?? []),
    ...(item.appliesToTools ?? []),
    ...(item.aliases ?? []),
  ].filter(Boolean).join(" ").toLowerCase();
}

export function filterComposerSkillMentions(items: ComposerSkillItem[], query: string, limit = 12): ComposerSkillItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return items.slice(0, limit);
  return items.filter((item) => composerSkillSearchText(item).includes(q)).slice(0, limit);
}

export function composerSkillMentionDisplay(item: ComposerSkillItem): { label: string; description?: string } {
  const label = item.label || item.id;
  const details = [item.id, item.description && item.description !== label ? item.description : undefined].filter(Boolean).join(" - ");
  return { label, description: details || undefined };
}

export function composerSkillMentionWidget(item: ComposerSkillItem): DroppedWidget {
  return {
    id: item.id,
    type: "skill",
    label: item.label || item.id,
    enabled: true,
    widgetKind: "skill_prompt",
    sourceItemId: item.id,
    description: item.description,
    metadata: {
      source: "composer_at_mention",
      mention: {
        syntax: `@${item.id}`,
        skill_id: item.id,
      },
      skill: {
        id: item.id,
        label: item.label || item.id,
        description: item.description ?? null,
        triggers: item.triggers ?? [],
        applies_to_tools: item.appliesToTools ?? [],
        aliases: item.aliases ?? [],
      },
    },
  };
}

function normalizeMentionToken(token: string): string {
  return token.trim().replace(/[.,!?;:)\]}]+$/g, "");
}

function normalizedMentionAliases(item: ComposerExtensionItem | ComposerSkillItem): string[] {
  const label = String(item.label ?? "").trim();
  const composerLabel = "ui" in item ? String(item.ui?.composer_label ?? "").trim() : "";
  const aliases = "aliases" in item && Array.isArray(item.aliases) ? item.aliases : [];
  return [
    item.id,
    item.id.split("/").pop() ?? "",
    label,
    label.replace(/\s+/g, "_"),
    composerLabel,
    composerLabel.replace(/\s+/g, "_"),
    ...aliases,
    ...aliases.map((alias) => alias.replace(/\s+/g, "_")),
  ].filter(Boolean).map((value) => value.toLowerCase());
}

export function toolMentionIdsFromText(text: string, items: ComposerExtensionItem[]): string[] {
  const lookup = new Map<string, string>();
  for (const item of items) {
    if (item.disabled) continue;
    for (const alias of normalizedMentionAliases(item)) {
      if (!lookup.has(alias)) lookup.set(alias, item.id);
    }
  }

  const ids: string[] = [];
  const seen = new Set<string>();
  for (const match of text.matchAll(/(?:^|\s)@([^\s@]+)/g)) {
    const token = normalizeMentionToken(match[1]).toLowerCase();
    const id = lookup.get(token);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    ids.push(id);
  }
  return ids;
}

export function skillMentionIdsFromText(text: string, items: ComposerSkillItem[]): string[] {
  const lookup = new Map<string, string>();
  for (const item of items) {
    for (const alias of normalizedMentionAliases(item)) {
      if (!lookup.has(alias)) lookup.set(alias, item.id);
    }
  }

  const ids: string[] = [];
  const seen = new Set<string>();
  for (const match of text.matchAll(/(?:^|\s)@([^\s@]+)/g)) {
    const token = normalizeMentionToken(match[1]).toLowerCase();
    const id = lookup.get(token);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    ids.push(id);
  }
  return ids;
}

export function isSafeLocalEndpoint(endpoint: string): boolean {
  return endpoint.startsWith("/api/") && !endpoint.startsWith("//") && !/^https?:\/\//i.test(endpoint);
}

function composerEndpointActionKey(action: Extract<ComposerWidgetAction, { type: "call_endpoint" }>): string {
  return `${(action.method ?? "GET").toUpperCase()} ${action.endpoint}`;
}

export function canExecuteComposerEndpointAction(action: ComposerWidgetAction): boolean {
  return action.type === "call_endpoint"
    && !action.requires_approval
    && isSafeLocalEndpoint(action.endpoint)
    && COMPOSER_ENDPOINT_ACTION_ALLOWLIST.has(composerEndpointActionKey(action));
}
