import type {
  ComposerCommandMode,
  ComposerWidgetAction,
  TemplateAiInput,
  TemplateCatalogMetadataItem,
  TemplateComposerInput,
  TemplateToolPolicy,
  UICatalog,
} from "./api";
import type { ComposerExtensionItem, DroppedWidget } from "../renderers/types";

export type TemplateToolPolicySettings = {
  id: string | null;
  defaultEnabledToolIds: string[];
  defaultDisabledToolIds: string[];
  allowedToolIds: string[];
  deniedToolIds: string[];
  toolChoice?: "auto" | "none" | "required" | Record<string, unknown>;
  parallelToolCalls?: boolean;
};

const TOOL_CHOICE_VALUES = new Set(["auto", "none", "required"]);

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function nonEmptyString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map(nonEmptyString).filter(Boolean))];
}

function modesMatch(item: { modes?: ComposerCommandMode[] }, mode: ComposerCommandMode): boolean {
  return !item.modes?.length || item.modes.includes(mode);
}

function itemEnabled(item: { enabled?: boolean }): boolean {
  return item.enabled !== false;
}

function firstActive<T extends { enabled?: boolean; modes?: ComposerCommandMode[] }>(
  items: T[] | undefined,
  mode: ComposerCommandMode,
): T | null {
  return items?.find((item) => itemEnabled(item) && modesMatch(item, mode)) ?? null;
}

export function selectTemplateAiInput(catalog: UICatalog | null | undefined, mode: ComposerCommandMode): TemplateAiInput | null {
  return firstActive(catalog?.ai_inputs, mode);
}

export function selectTemplateComposerInput(
  catalog: UICatalog | null | undefined,
  mode: ComposerCommandMode,
  aiInput: TemplateAiInput | null,
): TemplateComposerInput | null {
  const inputs = catalog?.composer_inputs ?? [];
  const requestedId = nonEmptyString(aiInput?.composer_input_id) || nonEmptyString(aiInput?.composer_input);
  if (requestedId) {
    const requested = inputs.find((item) => item.id === requestedId && itemEnabled(item) && modesMatch(item, mode));
    if (requested) return requested;
  }
  return firstActive(inputs, mode);
}

export function selectTemplateToolPolicy(
  catalog: UICatalog | null | undefined,
  mode: ComposerCommandMode,
  aiInput: TemplateAiInput | null,
): TemplateToolPolicy | null {
  const policies = catalog?.tool_policies ?? [];
  const requestedId = nonEmptyString(aiInput?.tool_policy_id) || nonEmptyString(aiInput?.tool_policy);
  if (requestedId) {
    const requested = policies.find((item) => item.id === requestedId && itemEnabled(item) && modesMatch(item, mode));
    if (requested) return requested;
  }
  return firstActive(policies, mode);
}

function policySource(policy: TemplateToolPolicy | null): Record<string, unknown> {
  if (!policy) return {};
  return objectRecord(policy.policy) ?? policy as unknown as Record<string, unknown>;
}

function toolChoice(value: unknown): TemplateToolPolicySettings["toolChoice"] {
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    return TOOL_CHOICE_VALUES.has(normalized) ? normalized as "auto" | "none" | "required" : undefined;
  }
  return objectRecord(value) ?? undefined;
}

export function templateToolPolicySettings(policy: TemplateToolPolicy | null): TemplateToolPolicySettings {
  const source = policySource(policy);
  return {
    id: policy?.id ?? null,
    defaultEnabledToolIds: stringList(source.default_enabled_tools ?? source.defaultEnabledTools),
    defaultDisabledToolIds: stringList(source.default_disabled_tools ?? source.defaultDisabledTools),
    allowedToolIds: stringList(source.allowed_tools ?? source.allowlist ?? source.tool_allowlist),
    deniedToolIds: stringList(source.denied_tools ?? source.denylist ?? source.tool_denylist),
    toolChoice: toolChoice(source.tool_choice),
    parallelToolCalls: typeof source.parallel_tool_calls === "boolean" ? source.parallel_tool_calls : undefined,
  };
}

function templateWidgetPayload(item: TemplateCatalogMetadataItem): Record<string, unknown> {
  return objectRecord(item.widget) ?? item;
}

function templateWidgetRefIds(input: TemplateAiInput | TemplateComposerInput | null): string[] {
  const raw = objectRecord(input)?.widgets;
  return stringList(raw);
}

function widgetAction(toolId: string): ComposerWidgetAction {
  return { type: "toggle_tool", tool_id: toolId };
}

export function templateComposerWidgetsForInput(
  catalog: UICatalog | null | undefined,
  aiInput: TemplateAiInput | null,
  composerInput: TemplateComposerInput | null,
  tools: ComposerExtensionItem[],
): DroppedWidget[] {
  const widgets = catalog?.composer_widgets ?? [];
  const requestedWidgetIds = new Set([
    ...templateWidgetRefIds(aiInput),
    ...templateWidgetRefIds(composerInput),
  ]);
  const toolById = new Map(tools.map((tool) => [tool.id, tool]));

  return widgets
    .filter((item) => item.enabled !== false)
    .filter((item) => requestedWidgetIds.size === 0 || (item.id && requestedWidgetIds.has(item.id)))
    .map<DroppedWidget | null>((item) => {
      const payload = templateWidgetPayload(item);
      const kind = nonEmptyString(payload.widgetKind) || nonEmptyString(payload.widget_kind) || nonEmptyString(item.widgetKind) || nonEmptyString(item.widget_kind);
      if (kind && kind !== "tool_toggle") return null;
      const toolId = (
        nonEmptyString(payload.tool_id)
        || nonEmptyString(payload.sourceItemId)
        || nonEmptyString(payload.source_item_id)
        || nonEmptyString(item.tool_id)
        || nonEmptyString(item.sourceItemId)
        || nonEmptyString(item.source_item_id)
      );
      const tool = toolId ? toolById.get(toolId) : null;
      if (!tool) return null;
      const label = nonEmptyString(payload.label) || nonEmptyString(item.label) || tool.ui?.composer_label || tool.label || tool.id;
      const description = nonEmptyString(payload.description) || nonEmptyString(item.description) || tool.ui?.composer_description || tool.description;
      const widget: DroppedWidget = {
        id: nonEmptyString(payload.id) || item.id || tool.id,
        type: "tool",
        label,
        description,
        enabled: payload.enabled !== false,
        widgetKind: "tool_toggle",
        action: widgetAction(tool.id),
        sourceItemId: tool.id,
        icon: nonEmptyString(payload.icon) || tool.ui?.composer_icon || tool.ui?.item_icon || tool.ui?.group_icon,
        metadata: {
          source: "template_catalog_widget",
          template_id: item.template_id ?? null,
          piece_id: item.piece_id ?? null,
          widget_id: item.id ?? null,
          tool: {
            id: tool.id,
            label: tool.label,
            category: tool.category ?? null,
            tags: tool.tags ?? [],
          },
        },
      };
      return widget;
    })
    .filter((widget): widget is DroppedWidget => widget !== null);
}
