import type { ComposerWidgetAction, ComposerWidgetKind } from "./api";
import type { ComposerExtensionItem, ComposerSkillItem, DroppedWidget } from "../renderers/types";
import { extractMentionTokens } from "./mentionContract";
import { supportedComposerDropKind, supportsComposerToggleDrop } from "./toolUi";

export type ComposerDropAction =
  | { type: "select_model"; profileId: string }
  | { type: "drop_widget"; widget: DroppedWidget }
  | { type: "ignore" };

export type ComposerMentionMetadata = {
  id: string;
  kind: "file" | "service" | "skill" | "tool";
  label: string;
  syntax: string;
};

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
  return [
    item.id,
    item.label,
    item.description,
    item.ui?.composer_label,
    item.ui?.composer_description,
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
  return { label, description: description && description !== label ? description : undefined };
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
        id: item.id,
        kind: "tool",
        label,
        syntax: `@${label}`,
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
  return {
    label,
    description: item.description && item.description !== label ? item.description : undefined,
  };
}

export function composerSkillMentionWidget(item: ComposerSkillItem): DroppedWidget {
  const label = item.label || item.id;
  return {
    id: item.id,
    type: "skill",
    label,
    enabled: true,
    widgetKind: "skill_prompt",
    sourceItemId: item.id,
    description: item.description,
    metadata: {
      source: "composer_at_mention",
      mention: {
        id: item.id,
        kind: "skill",
        label,
        syntax: `@${label}`,
        skill_id: item.id,
      },
      skill: {
        id: item.id,
        label,
        description: item.description ?? null,
        triggers: item.triggers ?? [],
        applies_to_tools: item.appliesToTools ?? [],
        aliases: item.aliases ?? [],
      },
    },
  };
}

export function composerFileMentionWidget(file: string): DroppedWidget {
  return {
    id: `mention-file:${file}`,
    type: "file",
    label: file,
    enabled: true,
    widgetKind: "file_reference",
    sourceItemId: file,
    description: "workspace file",
    metadata: {
      source: "composer_at_mention",
      mention: {
        file_path: file,
        id: file,
        kind: "file",
        label: file,
        syntax: `@${file}`,
      },
    },
  };
}

export function composerServiceMentionWidget(service: {
  description?: string;
  id: string;
  label: string;
  toolIds: string[];
}): DroppedWidget {
  return {
    id: `mention-service:${service.id}`,
    type: "service",
    label: service.label,
    enabled: true,
    widgetKind: "service_reference",
    sourceItemId: service.id,
    description: service.description,
    metadata: {
      source: "composer_at_mention",
      mention: {
        id: service.id,
        kind: "service",
        label: service.label,
        syntax: `@${service.label}`,
      },
      service: {
        id: service.id,
        label: service.label,
        tool_ids: service.toolIds,
      },
    },
  };
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

function uniqueMentionLookup(
  items: Array<ComposerExtensionItem | ComposerSkillItem>,
): Map<string, string> {
  const owners = new Map<string, Set<string>>();
  for (const item of items) {
    for (const alias of normalizedMentionAliases(item)) {
      const current = owners.get(alias) ?? new Set<string>();
      current.add(item.id);
      owners.set(alias, current);
    }
  }
  const lookup = new Map<string, string>();
  for (const [alias, ids] of owners) {
    if (ids.size === 1) lookup.set(alias, [...ids][0]);
  }
  return lookup;
}

export function composerMentionMetadataFromWidgets(
  widgets: DroppedWidget[],
): ComposerMentionMetadata[] {
  const result: ComposerMentionMetadata[] = [];
  const seen = new Set<string>();
  for (const widget of widgets) {
    if (widget.metadata?.source !== "composer_at_mention") continue;
    const mention = widget.metadata.mention;
    if (!mention || typeof mention !== "object" || Array.isArray(mention)) continue;
    const record = mention as Record<string, unknown>;
    const kind = String(record.kind ?? widget.type);
    if (!["file", "service", "skill", "tool"].includes(kind)) continue;
    const id = String(
      record.id
      ?? record.tool_id
      ?? record.skill_id
      ?? record.file_path
      ?? widget.sourceItemId
      ?? widget.id,
    ).trim();
    const label = String(record.label ?? widget.label ?? id).trim();
    if (!id || !label || seen.has(`${kind}:${id}`)) continue;
    seen.add(`${kind}:${id}`);
    result.push({
      id,
      kind: kind as ComposerMentionMetadata["kind"],
      label,
      syntax: String(record.syntax ?? `@${label}`),
    });
  }
  return result;
}

export function normalizeComposerMentionMetadata(
  value: unknown,
): ComposerMentionMetadata[] {
  if (!Array.isArray(value)) return [];
  const result: ComposerMentionMetadata[] = [];
  const seen = new Set<string>();
  for (const item of value) {
    if (!item || typeof item !== "object" || Array.isArray(item)) continue;
    const record = item as Record<string, unknown>;
    const kind = String(record.kind ?? "");
    const id = String(record.id ?? "").trim();
    const label = String(record.label ?? "").trim();
    if (!["file", "service", "skill", "tool"].includes(kind) || !id || !label) continue;
    if (seen.has(`${kind}:${id}`)) continue;
    seen.add(`${kind}:${id}`);
    result.push({
      id,
      kind: kind as ComposerMentionMetadata["kind"],
      label,
      syntax: String(record.syntax ?? `@${label}`),
    });
  }
  return result;
}

export function toolMentionIdsFromText(text: string, items: ComposerExtensionItem[]): string[] {
  const lookup = uniqueMentionLookup(items.filter((item) => !item.disabled));

  const ids: string[] = [];
  const seen = new Set<string>();
  for (const mention of extractMentionTokens(text)) {
    const token = mention.value.toLowerCase();
    const id = lookup.get(token);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    ids.push(id);
  }
  return ids;
}

export function skillMentionIdsFromText(text: string, items: ComposerSkillItem[]): string[] {
  const lookup = uniqueMentionLookup(items);

  const ids: string[] = [];
  const seen = new Set<string>();
  for (const mention of extractMentionTokens(text)) {
    const token = mention.value.toLowerCase();
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
