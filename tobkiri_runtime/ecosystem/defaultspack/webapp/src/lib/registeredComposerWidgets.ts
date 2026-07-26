import type { UICatalog } from "./api";
import type { VerifiedFrontendContribution } from "../host/frontendContracts";
import type { DroppedWidget } from "../renderers/types";

export type RegisteredComposerWidgetDescriptor = {
  actionId?: string;
  actionOperation: string;
  dataSourceId?: string;
  panelId?: string;
  queryOperation: string;
  ownerPackId?: string;
  requestedValueScope: "draft" | "conversation" | "run" | "settings" | "workspace" | "global";
};

export type ResolvedRegisteredComposerWidget = {
  descriptor: RegisteredComposerWidgetDescriptor;
  action?: VerifiedFrontendContribution;
  dataSource?: VerifiedFrontendContribution;
  panel?: VerifiedFrontendContribution;
  profileId: string;
  planHash: string;
};

export type ComposerSelectorItem = {
  id: string;
  label: string;
  description?: string;
  disabled: boolean;
  disabledReason?: string;
};

export type ComposerSelectorPage = {
  items: ComposerSelectorItem[];
  nextCursor: string | null;
};

const REGISTERED_WIDGET_METADATA_KEY = "registered_composer_widget";
const VALUE_SCOPES = new Set<RegisteredComposerWidgetDescriptor["requestedValueScope"]>([
  "draft",
  "conversation",
  "run",
  "settings",
  "workspace",
  "global",
]);

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function cleanString(value: unknown, maxLength = 160): string {
  return typeof value === "string" ? value.trim().slice(0, maxLength) : "";
}

function descriptorFromRecord(
  value: Record<string, unknown>,
): RegisteredComposerWidgetDescriptor | null {
  const actionId = cleanString(value.action_id ?? value.actionId);
  const dataSourceId = cleanString(value.data_source ?? value.dataSourceId);
  const panelId = cleanString(value.panel_id ?? value.panelId ?? value.renderer_id);
  const ownerPackId = cleanString(value.owner_pack_id ?? value.ownerPackId);
  const rawScope = cleanString(value.value_scope ?? value.valueScope) as RegisteredComposerWidgetDescriptor["requestedValueScope"];
  const requestedValueScope = VALUE_SCOPES.has(rawScope) ? rawScope : "draft";
  if (!actionId && !dataSourceId && !panelId) return null;
  return {
    ...(actionId ? { actionId } : {}),
    ...(dataSourceId ? { dataSourceId } : {}),
    ...(panelId ? { panelId } : {}),
    ...(ownerPackId ? { ownerPackId } : {}),
    actionOperation: cleanString(value.action_operation ?? value.actionOperation) || "invoke",
    queryOperation: cleanString(value.query_operation ?? value.queryOperation) || "query",
    requestedValueScope,
  };
}

export function registeredComposerWidgetMetadata(
  payload: Record<string, unknown>,
): Record<string, unknown> | null {
  const descriptor = descriptorFromRecord(payload);
  return descriptor ? { [REGISTERED_WIDGET_METADATA_KEY]: descriptor } : null;
}

export function registeredComposerWidgetDescriptor(
  widget: DroppedWidget,
): RegisteredComposerWidgetDescriptor | null {
  const metadata = objectRecord(widget.metadata);
  const value = metadata ? objectRecord(metadata[REGISTERED_WIDGET_METADATA_KEY]) : null;
  return value ? descriptorFromRecord(value) : null;
}

function contributionFor(
  catalog: UICatalog | null | undefined,
  id: string | undefined,
  kind: VerifiedFrontendContribution["kind"] | Array<VerifiedFrontendContribution["kind"]>,
  ownerPackId?: string,
): VerifiedFrontendContribution | undefined {
  if (!id || !catalog?.dynamic_host) return undefined;
  const kinds = new Set(Array.isArray(kind) ? kind : [kind]);
  const matches = catalog.dynamic_host.contributions.filter((item) => (
    item.contribution_id === id
    && kinds.has(item.kind)
    && item.resolved_plan_hash === catalog.dynamic_host?.plan_hash
    && item.resolved_profile_revision === catalog.dynamic_host?.profile_revision
    && !catalog.dynamic_host?.quarantined_pack_ids.includes(item.owner_pack_id)
    && (!ownerPackId || item.owner_pack_id === ownerPackId)
  ));
  return matches.length === 1 ? matches[0] : undefined;
}

export function resolveRegisteredComposerWidget(
  widget: DroppedWidget,
  catalog: UICatalog | null | undefined,
): ResolvedRegisteredComposerWidget | null {
  const descriptor = registeredComposerWidgetDescriptor(widget);
  const host = catalog?.dynamic_host;
  if (!descriptor || !host) return null;
  const action = contributionFor(catalog, descriptor.actionId, "action", descriptor.ownerPackId);
  const dataSource = contributionFor(catalog, descriptor.dataSourceId, "data_source", descriptor.ownerPackId);
  const panel = contributionFor(
    catalog,
    descriptor.panelId,
    ["renderer", "route"],
    descriptor.ownerPackId,
  );
  if (descriptor.actionId && (!action?.action_contract || action.mode !== "declarative")) return null;
  if (descriptor.dataSourceId && (!dataSource?.data_source_contract || dataSource.mode !== "declarative")) return null;
  if (descriptor.panelId && (!panel?.view || panel.mode !== "declarative")) return null;
  const owners = [action, dataSource, panel]
    .filter((item): item is VerifiedFrontendContribution => Boolean(item))
    .map((item) => item.owner_pack_id);
  if (owners.length > 1 && new Set(owners).size !== 1) return null;
  return {
    descriptor,
    ...(action ? { action } : {}),
    ...(dataSource ? { dataSource } : {}),
    ...(panel ? { panel } : {}),
    profileId: host.profile_id,
    planHash: host.plan_hash,
  };
}

export function registeredWidgetKindIsResolvable(
  kind: string,
  payload: Record<string, unknown>,
  catalog: UICatalog | null | undefined,
): boolean {
  const metadata = registeredComposerWidgetMetadata(payload);
  if (!metadata) return false;
  const widget: DroppedWidget = {
    id: "candidate",
    type: kind,
    label: "candidate",
    widgetKind: kind,
    metadata,
  };
  const resolved = resolveRegisteredComposerWidget(widget, catalog);
  if (!resolved) return false;
  if (kind === "button") return Boolean(resolved.action);
  if (kind === "selector") return Boolean(resolved.action && resolved.dataSource);
  if (kind === "panel") return Boolean(resolved.panel);
  return false;
}

export function normalizeComposerSelectorPage(value: unknown): ComposerSelectorPage {
  const root = objectRecord(value);
  const data = objectRecord(root?.data) ?? root;
  const rawItems = Array.isArray(data?.items)
    ? data.items
    : Array.isArray(data?.results)
      ? data.results
      : Array.isArray(data?.options)
        ? data.options
        : [];
  const seen = new Set<string>();
  const items: ComposerSelectorItem[] = [];
  for (const raw of rawItems.slice(0, 100)) {
    const item = objectRecord(raw);
    if (!item) continue;
    const id = cleanString(item.id ?? item.value ?? item.key);
    const label = cleanString(item.label ?? item.name ?? item.title);
    if (!id || !label || seen.has(id)) continue;
    seen.add(id);
    const disabledReason = cleanString(item.disabled_reason ?? item.disabledReason, 240);
    items.push({
      id,
      label,
      ...(cleanString(item.description, 500)
        ? { description: cleanString(item.description, 500) }
        : {}),
      disabled: item.disabled === true || Boolean(disabledReason),
      ...(disabledReason ? { disabledReason } : {}),
    });
  }
  return {
    items,
    nextCursor: cleanString(data?.next_cursor ?? data?.nextCursor) || null,
  };
}
