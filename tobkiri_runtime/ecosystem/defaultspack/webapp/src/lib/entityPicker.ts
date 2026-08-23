import type { TemplateCatalogMetadataItem, UICatalog } from "./api";
import type { FrontendContributionKind, VerifiedFrontendContribution } from "../host/frontendContracts";

export const ENTITY_PICKER_API_VERSION = "rumi.entity_picker.v1";
export const ENTITY_PICKER_DATA_SOURCE_CONTRACT = "tobkiri.data.entity-picker.v1";
export const ENTITY_PICKER_ACTION_CONTRACT = "rumi.action.entity-picker.v1";

export type EntityPickerSelectionMode = "single" | "multi";
export type EntityPickerPresentation = "popup" | "palette" | "inline" | "settings" | "status_surface";
export type EntityPickerValueScope = "draft" | "conversation" | "run" | "settings" | "workspace" | "global";

export type EntityPickerDiagnostic = {
  code: string;
  message: string;
  pickerId: string;
  path?: string;
  templateId?: string;
  sourcePackId?: string;
  trustLevel?: string;
};

export type EntityPickerItem = {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  group?: string;
  badges: string[];
  disabled: boolean;
  disabledReason?: string;
  favorite: boolean;
  recent: boolean;
  fixed?: boolean;
  create?: boolean;
};

export type EntityPickerCapabilityBinding = {
  profileId: string;
  planHash: string;
  catalogHash: string;
  contributionId: string;
  ownerPackId: string;
  contractId: typeof ENTITY_PICKER_DATA_SOURCE_CONTRACT | typeof ENTITY_PICKER_ACTION_CONTRACT;
};

export type ResolvedEntityPicker = {
  id: string;
  apiVersion: typeof ENTITY_PICKER_API_VERSION;
  label: string;
  description?: string;
  triggerCommand?: string;
  presentation: EntityPickerPresentation;
  selectionMode: EntityPickerSelectionMode;
  valueScope: EntityPickerValueScope;
  searchable: boolean;
  placeholder: string;
  dataSourceId: string;
  remote: boolean;
  dataSourceCapability?: EntityPickerCapabilityBinding;
  optimistic: boolean;
  selectActionId?: string;
  selectActionCapability?: EntityPickerCapabilityBinding;
  createActionId?: string;
  createActionCapability?: EntityPickerCapabilityBinding;
  sourceRevision?: string;
  nextCursor?: string;
  items: EntityPickerItem[];
  selectedIds: string[];
  itemPaths: EntityPickerItemPaths;
  maxItems: number;
  templateId?: string;
  sourcePackId?: string;
  trustLevel?: string;
  diagnostics: EntityPickerDiagnostic[];
  unsupported: boolean;
};

export type EntityPickerItemPaths = {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  group?: string;
  badges?: string;
  disabled?: string;
  disabledReason?: string;
  favorite?: string;
  recent?: string;
};

export type EntityPickerSelectionRequest = {
  pickerId: string;
  selectedIds: string[];
  actionId?: string;
  valueScope: EntityPickerValueScope;
  dataSourceId: string;
  sourceRevision?: string;
  query?: string;
};

export type EntityPickerPageRequest = {
  pickerId: string;
  query: string;
  cursor?: string;
  dataSourceId: string;
  sourceRevision?: string;
};

export type EntityPickerPage = {
  items: EntityPickerItem[];
  nextCursor?: string;
  sourceRevision?: string;
};

type JsonRecord = Record<string, unknown>;

const VALID_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const VALID_COMMAND = /^[a-z0-9][a-z0-9_-]{0,47}$/;
const PATH_SEGMENT = /^[A-Za-z_][A-Za-z0-9_-]{0,63}$/;
const BLOCKED_SEGMENTS = new Set(["__proto__", "constructor", "prototype"]);
const PRESENTATIONS = new Set<EntityPickerPresentation>(["popup", "palette", "inline", "settings", "status_surface"]);
const SCOPES = new Set<EntityPickerValueScope>(["draft", "conversation", "run", "settings", "workspace", "global"]);
const MAX_TEXT = 500;

function record(value: unknown): JsonRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : null;
}

function text(value: unknown, max = MAX_TEXT): string | undefined {
  if (typeof value !== "string" && typeof value !== "number") return undefined;
  const normalized = String(value).trim();
  return normalized ? normalized.slice(0, max) : undefined;
}

function safeId(value: unknown): string | undefined {
  const valueText = text(value, 128);
  return valueText && VALID_ID.test(valueText) ? valueText : undefined;
}

function safePath(value: unknown): string | undefined {
  const valueText = text(value, 256);
  if (!valueText) return undefined;
  const parts = valueText.split(".");
  return parts.length <= 12 && parts.every((part) => PATH_SEGMENT.test(part) && !BLOCKED_SEGMENTS.has(part))
    ? valueText
    : undefined;
}

function bool(value: unknown): boolean {
  return value === true || value === 1 || value === "true";
}

function integer(value: unknown, fallback: number, max: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? Math.min(parsed, max) : fallback;
}

export function readEntityPickerPath(source: unknown, path: string | undefined): unknown {
  const normalizedPath = safePath(path);
  if (!normalizedPath) return undefined;
  let current: unknown = source;
  for (const segment of normalizedPath.split(".")) {
    const currentRecord = record(current);
    if (!currentRecord || !Object.prototype.hasOwnProperty.call(currentRecord, segment)) return undefined;
    current = currentRecord[segment];
  }
  return current;
}

function stringList(value: unknown, limit = 20): string[] {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.slice(0, limit).map((item) => text(item, 120)).filter((item): item is string => Boolean(item)))];
}

function identity(item: TemplateCatalogMetadataItem, ...keys: string[]): string[] {
  return keys.map((key) => safeId(item[key])).filter((item): item is string => Boolean(item));
}

function actionMap(catalog: UICatalog | null | undefined): Map<string, TemplateCatalogMetadataItem> {
  const result = new Map<string, TemplateCatalogMetadataItem>();
  for (const action of catalog?.actions ?? []) {
    for (const id of identity(action, "action_id", "id", "command_id", "name")) {
      if (!result.has(id)) result.set(id, action);
    }
  }
  return result;
}

function sourceMap(catalog: UICatalog | null | undefined): Map<string, TemplateCatalogMetadataItem> {
  const result = new Map<string, TemplateCatalogMetadataItem>();
  for (const source of catalog?.data_sources ?? []) {
    for (const id of identity(source, "data_source", "source", "id")) {
      if (!result.has(id)) result.set(id, source);
    }
  }
  return result;
}

function provenance(raw: TemplateCatalogMetadataItem) {
  return {
    templateId: text(raw.template_id, 160),
    sourcePackId: text(raw.source_pack_id ?? record(raw.origin)?.pack_id, 160),
    trustLevel: text(raw.trust_level, 40),
  };
}

function capabilityBinding(
  catalog: UICatalog | null | undefined,
  metadata: TemplateCatalogMetadataItem | undefined,
  referenceId: string | undefined,
  expectedKind: Extract<FrontendContributionKind, "action" | "data_source">,
  picker: TemplateCatalogMetadataItem,
  pickerId: string,
  diagnostics: EntityPickerDiagnostic[],
  path: string,
): EntityPickerCapabilityBinding | undefined {
  if (!referenceId || !metadata) return undefined;
  const dynamic = catalog?.dynamic_host;
  const operationId = safeId(metadata.operation_id ?? metadata.function_id ?? referenceId);
  const pickerPackId = provenance(picker).sourcePackId;
  const metadataPackId = provenance(metadata).sourcePackId;
  const contributionId = safeId(
    metadata.contribution_id
      ?? (metadataPackId && operationId
        ? `pack.${metadataPackId}.${operationId}`
        : referenceId),
  );
  const matches = dynamic?.contributions.filter((contribution) => (
    contribution.contribution_id === contributionId
    && contribution.kind === expectedKind
    && contribution.operation_id === operationId
    && contribution.resolved_plan_hash === dynamic.plan_hash
  )) ?? [];
  const contribution: VerifiedFrontendContribution | undefined = matches.length === 1
    ? matches[0]
    : undefined;
  const contractId = expectedKind === "action"
    ? contribution?.action_contract
    : contribution?.data_source_contract;
  const expectedContract = expectedKind === "action"
    ? ENTITY_PICKER_ACTION_CONTRACT
    : ENTITY_PICKER_DATA_SOURCE_CONTRACT;
  if (
    !dynamic
    || !contribution
    || !operationId
    || contractId !== expectedContract
    || (pickerPackId && contribution.owner_pack_id !== pickerPackId)
    || (metadataPackId && contribution.owner_pack_id !== metadataPackId)
  ) {
    diagnostics.push(diagnostic(
      picker,
      pickerId,
      "entity_picker.unbound_capability",
      `${expectedKind} is not bound to the active ProfileLock/ResolvedPlan catalog`,
      path,
    ));
    return undefined;
  }
  return {
    profileId: dynamic.profile_id,
    planHash: dynamic.plan_hash,
    catalogHash: dynamic.catalog_hash,
    contributionId: contribution.contribution_id,
    ownerPackId: contribution.owner_pack_id,
    contractId: expectedContract,
  };
}

function diagnostic(raw: TemplateCatalogMetadataItem, pickerId: string, code: string, message: string, path?: string): EntityPickerDiagnostic {
  return { pickerId, code, message, ...(path ? { path } : {}), ...provenance(raw) };
}

function payload(raw: TemplateCatalogMetadataItem): JsonRecord {
  return record(raw.picker) ?? raw;
}

function itemPaths(config: JsonRecord, diagnostics: EntityPickerDiagnostic[], raw: TemplateCatalogMetadataItem, pickerId: string): EntityPickerItemPaths {
  const required = {
    id: config.id_path ?? "id",
    label: config.label_path ?? "label",
  };
  const optional: Record<string, unknown> = {
    description: config.description_path,
    icon: config.icon_path,
    group: config.group_by_path ?? config.group_path,
    badges: config.badges_path,
    disabled: config.disabled_path,
    disabledReason: config.disabled_reason_path,
    favorite: config.favorite_path,
    recent: config.recent_path,
  };
  const result: EntityPickerItemPaths = { id: "id", label: "label" };
  for (const [key, value] of Object.entries({ ...required, ...optional })) {
    if (value === undefined) continue;
    const normalized = safePath(value);
    if (!normalized) {
      diagnostics.push(diagnostic(raw, pickerId, "entity_picker.invalid_path", `invalid item path: ${key}`, `${key}_path`));
      continue;
    }
    (result as unknown as JsonRecord)[key] = normalized;
  }
  return result;
}

function normalizeOneItem(candidate: unknown, paths: EntityPickerItemPaths): EntityPickerItem | null {
  const item = record(candidate);
  if (!item) return null;
  const id = safeId(readEntityPickerPath(item, paths.id));
  const label = text(readEntityPickerPath(item, paths.label), 200);
  if (!id || !label) return null;
  return {
    id,
    label,
    description: text(readEntityPickerPath(item, paths.description)),
    icon: safeId(readEntityPickerPath(item, paths.icon)),
    group: text(readEntityPickerPath(item, paths.group), 120),
    badges: stringList(readEntityPickerPath(item, paths.badges), 8),
    disabled: bool(readEntityPickerPath(item, paths.disabled)),
    disabledReason: text(readEntityPickerPath(item, paths.disabledReason), 240),
    favorite: bool(readEntityPickerPath(item, paths.favorite)),
    recent: bool(readEntityPickerPath(item, paths.recent)),
  };
}

export function normalizeEntityPickerItems(
  picker: Pick<ResolvedEntityPicker, "itemPaths" | "maxItems">,
  rawItems: unknown,
): EntityPickerItem[] {
  if (!Array.isArray(rawItems)) return [];
  const seen = new Set<string>();
  return rawItems.slice(0, picker.maxItems).flatMap((candidate) => {
    const item = normalizeOneItem(candidate, picker.itemPaths);
    if (!item || seen.has(item.id)) return [];
    seen.add(item.id);
    return [item];
  });
}

function fixedItems(config: JsonRecord): EntityPickerItem[] {
  const raw = Array.isArray(config.fixed_entries) ? config.fixed_entries : [];
  return raw.slice(0, 20).flatMap((candidate) => {
    const item = typeof candidate === "string" ? { id: candidate, label: candidate } : record(candidate);
    if (!item) return [];
    const id = safeId(item.id ?? item.value);
    const label = text(item.label ?? id, 200);
    if (!id || !label) return [];
    return [{ id, label, description: text(item.description), badges: [], disabled: bool(item.disabled), disabledReason: text(item.disabled_reason, 240), favorite: false, recent: false, fixed: true }];
  });
}

function createItem(config: JsonRecord): EntityPickerItem | null {
  const create = record(config.create_item);
  if (!create) return null;
  return {
    id: "__create__",
    label: text(create.label, 200) ?? "Create new",
    description: text(create.description),
    icon: safeId(create.icon),
    badges: [],
    disabled: false,
    favorite: false,
    recent: false,
    fixed: true,
    create: true,
  };
}

function sourceItems(source: TemplateCatalogMetadataItem | undefined): unknown {
  if (!source) return [];
  const snapshot = record(source.snapshot) ?? record(source.data) ?? record(source.value) ?? source;
  return snapshot.items ?? snapshot.results ?? [];
}

function unsupportedPicker(raw: TemplateCatalogMetadataItem, id: string, diagnostics: EntityPickerDiagnostic[]): ResolvedEntityPicker {
  return {
    id,
    apiVersion: ENTITY_PICKER_API_VERSION,
    label: "Unsupported entity picker",
    description: diagnostics[0]?.message,
    presentation: "popup",
    selectionMode: "single",
    valueScope: "draft",
    searchable: false,
    placeholder: "Unavailable",
    dataSourceId: "unsupported",
    remote: false,
    optimistic: false,
    items: [],
    selectedIds: [],
    itemPaths: { id: "id", label: "label" },
    maxItems: 100,
    ...provenance(raw),
    diagnostics,
    unsupported: true,
  };
}

function resolveOne(
  raw: TemplateCatalogMetadataItem,
  catalog: UICatalog | null | undefined,
  sources: Map<string, TemplateCatalogMetadataItem>,
  actions: Map<string, TemplateCatalogMetadataItem>,
): ResolvedEntityPicker {
  const config = payload(raw);
  const id = safeId(config.picker_id ?? config.id ?? raw.id) ?? `invalid_${text(raw.piece_id, 60) ?? "picker"}`;
  const diagnostics: EntityPickerDiagnostic[] = [];
  const version = text(config.api_version, 80) ?? ENTITY_PICKER_API_VERSION;
  if (version !== ENTITY_PICKER_API_VERSION) diagnostics.push(diagnostic(raw, id, "entity_picker.incompatible_version", `unsupported API version: ${version}`, "api_version"));
  if (!safeId(config.picker_id ?? config.id ?? raw.id)) diagnostics.push(diagnostic(raw, id, "entity_picker.invalid_id", "picker ID must be an opaque ID", "id"));
  const dataSourceId = safeId(config.data_source);
  if (!dataSourceId) diagnostics.push(diagnostic(raw, id, "entity_picker.invalid_data_source", "data_source must be an opaque registered ID", "data_source"));
  const source = dataSourceId ? sources.get(dataSourceId) : undefined;
  if (dataSourceId && !source) diagnostics.push(diagnostic(raw, id, "entity_picker.unregistered_data_source", `unregistered data source: ${dataSourceId}`, "data_source"));
  const remote = bool(config.remote) || bool(source?.remote);
  const dataSourceCapability = remote ? capabilityBinding(
    catalog,
    source,
    dataSourceId,
    "data_source",
    raw,
    id,
    diagnostics,
    "data_source",
  ) : undefined;
  const paths = itemPaths(config, diagnostics, raw, id);
  const scopeText = text(config.value_scope, 40) as EntityPickerValueScope | undefined;
  const valueScope = scopeText && SCOPES.has(scopeText) ? scopeText : "draft";
  const persistent = valueScope === "settings" || valueScope === "workspace" || valueScope === "global";
  if (scopeText && !SCOPES.has(scopeText)) diagnostics.push(diagnostic(raw, id, "entity_picker.invalid_scope", `unsupported value scope: ${scopeText}`, "value_scope"));
  const selectActionId = safeId(config.on_select_action_id);
  const selectAction = selectActionId ? actions.get(selectActionId) : undefined;
  const selectActionCapability = capabilityBinding(
    catalog,
    selectAction,
    selectActionId,
    "action",
    raw,
    id,
    diagnostics,
    "on_select_action_id",
  );
  if (persistent && (!selectActionId || !selectAction || !selectActionCapability)) {
    diagnostics.push(diagnostic(raw, id, "entity_picker.unregistered_action", "persistent selection requires a registered executable action", "on_select_action_id"));
  } else if (selectActionId && (!selectAction || !selectActionCapability)) {
    diagnostics.push(diagnostic(raw, id, "entity_picker.unregistered_action", `unregistered select action: ${selectActionId}`, "on_select_action_id"));
  }
  const create = record(config.create_item);
  const createActionId = safeId(create?.action_id);
  const createAction = createActionId ? actions.get(createActionId) : undefined;
  const createActionCapability = capabilityBinding(
    catalog,
    createAction,
    createActionId,
    "action",
    raw,
    id,
    diagnostics,
    "create_item.action_id",
  );
  if (create && (!createActionId || !createAction || !createActionCapability)) diagnostics.push(diagnostic(raw, id, "entity_picker.unregistered_action", "create item requires a registered executable action", "create_item.action_id"));
  if (remote && !dataSourceCapability) diagnostics.push(diagnostic(raw, id, "entity_picker.unregistered_data_source", "remote source requires an active ProfileLock/ResolvedPlan capability", "data_source"));
  const trigger = text(config.trigger_command, 48)?.replace(/^\/+/, "").toLowerCase();
  if (trigger && !VALID_COMMAND.test(trigger)) diagnostics.push(diagnostic(raw, id, "entity_picker.invalid_trigger", "trigger command is invalid", "trigger_command"));
  if (diagnostics.length) return unsupportedPicker(raw, id, diagnostics);

  const maxItems = integer(config.max_items ?? source?.max_items, 200, 500);
  const partial: ResolvedEntityPicker = {
    id,
    apiVersion: ENTITY_PICKER_API_VERSION,
    label: text(config.label ?? config.title, 200) ?? id,
    description: text(config.description),
    triggerCommand: trigger,
    presentation: PRESENTATIONS.has(config.presentation as EntityPickerPresentation) ? config.presentation as EntityPickerPresentation : "popup",
    selectionMode: config.selection_mode === "multi" ? "multi" : "single",
    valueScope,
    searchable: config.searchable !== false,
    placeholder: text(config.placeholder, 200) ?? "Search items",
    dataSourceId: dataSourceId!,
    remote,
    dataSourceCapability,
    optimistic: valueScope === "draft" || valueScope === "conversation" || valueScope === "run" || bool(config.optimistic),
    selectActionId,
    selectActionCapability,
    createActionId,
    createActionCapability,
    sourceRevision: text(source?.revision ?? record(source?.snapshot)?.revision, 160),
    nextCursor: text(source?.next_cursor ?? record(source?.snapshot)?.next_cursor, 200),
    items: [],
    selectedIds: stringList(config.selected_ids, 100).filter((item) => VALID_ID.test(item)),
    itemPaths: paths,
    maxItems,
    ...provenance(raw),
    diagnostics: [],
    unsupported: false,
  };
  const normalized = normalizeEntityPickerItems(partial, sourceItems(source));
  const createEntry = createItem(config);
  const combined = [...(createEntry ? [createEntry] : []), ...fixedItems(config), ...normalized];
  const seen = new Set<string>();
  partial.items = combined.filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
  return partial;
}

export function resolveEntityPickers(catalog: UICatalog | null | undefined): ResolvedEntityPicker[] {
  const sources = sourceMap(catalog);
  const actions = actionMap(catalog);
  const seen = new Set<string>();
  return (catalog?.entity_pickers ?? [])
    .filter((item) => item.enabled !== false)
    .map((item) => resolveOne(item, catalog, sources, actions))
    .filter((picker) => {
      if (seen.has(picker.id)) return false;
      seen.add(picker.id);
      return true;
    });
}

export function entityPickerForCommand(
  pickers: ResolvedEntityPicker[],
  command: { id: string; name: string; aliases?: string[] },
): ResolvedEntityPicker | undefined {
  const names = new Set(
    [command.id, command.name, ...(command.aliases ?? [])]
      .map((value) => String(value ?? "").trim().toLowerCase())
      .filter(Boolean),
  );
  return pickers.find((picker) => picker.triggerCommand && names.has(picker.triggerCommand));
}

export function entityPickersForPresentation(
  pickers: ResolvedEntityPicker[],
  presentation: EntityPickerPresentation,
): ResolvedEntityPicker[] {
  return pickers.filter((picker) => (
    !picker.unsupported && picker.presentation === presentation
  ));
}

export function filterEntityPickerItems(items: EntityPickerItem[], query: string): EntityPickerItem[] {
  const normalized = query.trim().toLocaleLowerCase();
  const filtered = normalized
    ? items.filter((item) => [item.label, item.description, item.group, ...item.badges].filter(Boolean).join(" ").toLocaleLowerCase().includes(normalized))
    : items;
  return [...filtered].sort((left, right) => (
    Number(Boolean(right.create)) - Number(Boolean(left.create))
    || Number(right.favorite) - Number(left.favorite)
    || Number(right.recent) - Number(left.recent)
    || (left.group ?? "").localeCompare(right.group ?? "")
    || left.label.localeCompare(right.label)
    || left.id.localeCompare(right.id)
  ));
}
