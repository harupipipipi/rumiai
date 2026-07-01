import type { TemplateToolPolicy } from "./api";

export type TemplateToolPolicySettings = {
  id: string | null;
  ids: string[];
  projectedIds: string[];
  defaultEnabledToolIds: string[];
  defaultDisabledToolIds: string[];
  allowedToolIds: string[];
  hasAllowedToolRestriction: boolean;
  deniedToolIds: string[];
  selectedToolIds: string[];
  toolChoice?: "auto" | "none" | "required" | Record<string, unknown>;
  parallelToolCalls?: boolean;
  toggleable?: boolean;
  params?: Record<string, unknown>;
  diagnostics: Array<Record<string, unknown>>;
};

export type TemplateToolPolicyMergeOptions = {
  requestDisabledTools?: string[];
};

const TOOL_CHOICE_VALUES = new Set(["auto", "none", "required"]);
const ALLOWLIST_KEYS = ["allowedToolIds", "allowed_tool_ids", "allowed_tools", "allowlist", "tool_allowlist"];
const DENYLIST_KEYS = ["deniedToolIds", "denied_tool_ids", "denied_tools", "denylist", "tool_denylist", "tool_blocklist", "disabled_tools", "default_disabled_tools", "defaultDisabledTools"];
const DEFAULT_ENABLED_KEYS = ["default_enabled_tools", "defaultEnabledTools"];
const DEFAULT_DISABLED_KEYS = ["default_disabled_tools", "defaultDisabledTools"];
const SELECTED_TOOLS_KEYS = ["selected_tools", "selectedTools"];

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function nonEmptyString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function sortedUnique(values: unknown[]): string[] {
  return [...new Set(values.map(nonEmptyString).filter(Boolean))].sort();
}

function source(policy: TemplateToolPolicy | Record<string, unknown> | null): Record<string, unknown> {
  if (!policy) return {};
  const record = policy as Record<string, unknown>;
  return objectRecord(record.policy) ?? objectRecord(record.tool_policy) ?? record;
}

function stringList(value: unknown): string[] {
  if (typeof value === "string") return value.split(",").map((item) => item.trim()).filter(Boolean);
  if (!Array.isArray(value)) return [];
  return value.map(nonEmptyString).filter(Boolean);
}

function mergedStringList(record: Record<string, unknown>, keys: string[]): string[] {
  return sortedUnique(keys.flatMap((key) => stringList(record[key])));
}

function mergedStringListWithPresence(record: Record<string, unknown>, keys: string[]): [string[], boolean] {
  return [mergedStringList(record, keys), keys.some((key) => Object.prototype.hasOwnProperty.call(record, key))];
}

function toolChoice(value: unknown): TemplateToolPolicySettings["toolChoice"] {
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    return TOOL_CHOICE_VALUES.has(normalized) ? normalized as "auto" | "none" | "required" : undefined;
  }
  return objectRecord(value) ?? undefined;
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right)).map(([key, item]) => [key, canonical(item)]));
}

function canonicalString(value: unknown): string {
  return JSON.stringify(canonical(value));
}

function mergeToolChoice(values: Array<TemplateToolPolicySettings["toolChoice"]>, diagnostics: Array<Record<string, unknown>>): TemplateToolPolicySettings["toolChoice"] {
  const defined = values.filter((value): value is NonNullable<TemplateToolPolicySettings["toolChoice"]> => value !== undefined);
  if (!defined.length) return undefined;
  const first = defined[0];
  if (defined.every((value) => canonicalString(value) === canonicalString(first))) return first;
  if (defined.includes("none")) return "none";
  diagnostics.push({
    level: "warning",
    severity: "warning",
    code: "template.tool_policy.conflicting_tool_choice",
    message: "tool_choice values conflict across template tool policies; using auto",
  });
  return "auto";
}

function mergeBoolean(values: Array<boolean | undefined>): boolean | undefined {
  const defined = values.filter((value): value is boolean => typeof value === "boolean");
  if (!defined.length) return undefined;
  return defined.some((value) => value === false) ? false : true;
}

function mergeParams(values: Array<Record<string, unknown>>, diagnostics: Array<Record<string, unknown>>): Record<string, unknown> | undefined {
  const merged: Record<string, unknown> = {};
  const conflicts = new Set<string>();
  for (const params of values) {
    for (const [key, value] of Object.entries(params)) {
      if (conflicts.has(key)) continue;
      if (!(key in merged)) {
        merged[key] = value;
        continue;
      }
      if (canonicalString(merged[key]) === canonicalString(value)) continue;
      conflicts.add(key);
      delete merged[key];
      diagnostics.push({
        level: "warning",
        severity: "warning",
        code: "template.tool_policy.conflicting_param",
        message: `tool policy params.${key} conflicts across templates and was removed`,
        param: key,
      });
    }
  }
  return Object.keys(merged).length ? merged : undefined;
}

function sourceIds(policy: TemplateToolPolicy): string[] {
  const record = policy as Record<string, unknown>;
  const payload = source(policy);
  const metadata = objectRecord(policy.metadata);
  const metadataIds = sortedUnique(stringList(metadata?.source_ids));
  if (metadataIds.length) return metadataIds;
  return sortedUnique([
    policy.id,
    record.policy_id,
    record.tool_policy_id,
    payload.id,
    payload.policy_id,
    payload.tool_policy_id,
    ...stringList(metadata?.source_ids),
  ]);
}

function projectedIds(policy: TemplateToolPolicy): string[] {
  const record = policy as Record<string, unknown>;
  const payload = source(policy);
  return sortedUnique([record.projected_id, record.template_tool_policy_projected_id, payload.projected_id]);
}

function composedId(settings: Pick<TemplateToolPolicySettings, "ids" | "projectedIds">, policy: Record<string, unknown>): string {
  const canonicalPayload = canonicalString({
    source_ids: settings.ids,
    projected_ids: settings.projectedIds,
    policy,
  });
  let hash = 0x811c9dc5;
  for (let index = 0; index < canonicalPayload.length; index += 1) {
    hash ^= canonicalPayload.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return `composed_tool_policy:${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

export function templateToolPolicySettings(policy: TemplateToolPolicy | TemplateToolPolicy[] | null, options: TemplateToolPolicyMergeOptions = {}): TemplateToolPolicySettings {
  const policies = Array.isArray(policy) ? policy : policy ? [policy] : [];
  const diagnostics: Array<Record<string, unknown>> = policies.flatMap((item) => {
    const metadata = objectRecord(item.metadata);
    const values = metadata?.diagnostics;
    return Array.isArray(values)
      ? values.filter((value): value is Record<string, unknown> => Boolean(objectRecord(value)))
      : [];
  });
  const ids = sortedUnique(policies.flatMap(sourceIds));
  const projected = sortedUnique(policies.flatMap(projectedIds));
  const policySources = policies.map(source);
  const allowlists: string[][] = [];
  for (const policySource of policySources) {
    const [values, present] = mergedStringListWithPresence(policySource, ALLOWLIST_KEYS);
    if (present) allowlists.push(values);
  }
  const hasAllowedToolRestriction = allowlists.length > 0;
  const allowedToolIds = hasAllowedToolRestriction
    ? allowlists.slice(1).reduce((current, values) => current.filter((item) => values.includes(item)), allowlists[0] ?? [])
    : [];
  const deniedToolIds = sortedUnique([
    ...policySources.flatMap((item) => mergedStringList(item, DENYLIST_KEYS)),
    ...(options.requestDisabledTools ?? []),
  ]);
  const denied = new Set(deniedToolIds);
  const filteredAllowedToolIds = hasAllowedToolRestriction ? allowedToolIds.filter((toolId) => !denied.has(toolId)).sort() : [];
  const allowed = new Set(filteredAllowedToolIds);
  const defaultEnabledToolIds = sortedUnique(policySources.flatMap((item) => mergedStringList(item, DEFAULT_ENABLED_KEYS)))
    .filter((toolId) => !denied.has(toolId))
    .filter((toolId) => !hasAllowedToolRestriction || allowed.has(toolId));
  const defaultDisabledToolIds = sortedUnique([
    ...policySources.flatMap((item) => mergedStringList(item, DEFAULT_DISABLED_KEYS)),
    ...deniedToolIds,
  ]);
  const selectedToolIds = sortedUnique(policySources.flatMap((item) => mergedStringList(item, SELECTED_TOOLS_KEYS)))
    .filter((toolId) => !denied.has(toolId))
    .filter((toolId) => !hasAllowedToolRestriction || allowed.has(toolId));
  const params = mergeParams(policySources.map((item) => objectRecord(item.params) ?? {}), diagnostics);
  const policyShape: Record<string, unknown> = {};
  if (hasAllowedToolRestriction) policyShape.tool_allowlist = filteredAllowedToolIds;
  if (deniedToolIds.length) policyShape.tool_denylist = deniedToolIds;
  if (defaultEnabledToolIds.length) policyShape.default_enabled_tools = defaultEnabledToolIds;
  if (defaultDisabledToolIds.length) policyShape.default_disabled_tools = defaultDisabledToolIds;
  if (selectedToolIds.length) policyShape.selected_tools = selectedToolIds;
  const resolvedToolChoice = mergeToolChoice(policySources.map((item) => toolChoice(item.tool_choice)), diagnostics);
  if (resolvedToolChoice) policyShape.tool_choice = resolvedToolChoice;
  const parallelToolCalls = mergeBoolean(policySources.map((item) => typeof item.parallel_tool_calls === "boolean" ? item.parallel_tool_calls as boolean : undefined));
  if (typeof parallelToolCalls === "boolean") policyShape.parallel_tool_calls = parallelToolCalls;
  const toggleable = mergeBoolean(policySources.map((item) => typeof item.toggleable === "boolean" ? item.toggleable as boolean : undefined));
  if (typeof toggleable === "boolean") policyShape.toggleable = toggleable;
  if (params) policyShape.params = params;
  return {
    id: policies.length === 0 ? null : policies.length === 1 ? policies[0].id : composedId({ ids, projectedIds: projected }, policyShape),
    ids,
    projectedIds: projected,
    defaultEnabledToolIds,
    defaultDisabledToolIds,
    allowedToolIds: filteredAllowedToolIds,
    hasAllowedToolRestriction,
    deniedToolIds,
    selectedToolIds,
    toolChoice: resolvedToolChoice,
    parallelToolCalls,
    toggleable,
    params,
    diagnostics,
  };
}

export function mergeTemplateToolPolicies(items: TemplateToolPolicy[]): TemplateToolPolicy | null {
  if (!items.length) return null;
  if (items.length === 1) return items[0];
  const settings = templateToolPolicySettings(items);
  const policy: Record<string, unknown> = {};
  if (settings.hasAllowedToolRestriction) policy.tool_allowlist = settings.allowedToolIds;
  if (settings.deniedToolIds.length) policy.tool_denylist = settings.deniedToolIds;
  if (settings.defaultEnabledToolIds.length) policy.default_enabled_tools = settings.defaultEnabledToolIds;
  if (settings.defaultDisabledToolIds.length) policy.default_disabled_tools = settings.defaultDisabledToolIds;
  if (settings.selectedToolIds.length) policy.selected_tools = settings.selectedToolIds;
  if (settings.toolChoice) policy.tool_choice = settings.toolChoice;
  if (typeof settings.parallelToolCalls === "boolean") policy.parallel_tool_calls = settings.parallelToolCalls;
  if (typeof settings.toggleable === "boolean") policy.toggleable = settings.toggleable;
  if (settings.params) policy.params = settings.params;
  return {
    id: settings.id ?? "composed_tool_policy",
    label: items.find((item) => item.label)?.label,
    description: items.find((item) => item.description)?.description,
    policy,
    enabled: true,
    metadata: {
      ...(items[0]?.metadata ?? {}),
      ...(settings.ids.length ? { source_ids: settings.ids } : {}),
      ...(settings.projectedIds.length ? { projected_ids: settings.projectedIds } : {}),
      ...(settings.diagnostics.length ? { diagnostics: settings.diagnostics } : {}),
    },
  } as TemplateToolPolicy;
}

export function materializedTemplateToolPolicySettings(settings: TemplateToolPolicySettings): Record<string, unknown> {
  const policy: Record<string, unknown> = {};
  if (settings.hasAllowedToolRestriction) policy.tool_allowlist = settings.allowedToolIds;
  if (settings.deniedToolIds.length) policy.tool_denylist = settings.deniedToolIds;
  if (settings.defaultEnabledToolIds.length) policy.default_enabled_tools = settings.defaultEnabledToolIds;
  if (settings.defaultDisabledToolIds.length) policy.default_disabled_tools = settings.defaultDisabledToolIds;
  if (settings.selectedToolIds.length) policy.selected_tools = settings.selectedToolIds;
  if (settings.toolChoice) policy.tool_choice = settings.toolChoice;
  if (typeof settings.parallelToolCalls === "boolean") policy.parallel_tool_calls = settings.parallelToolCalls;
  if (typeof settings.toggleable === "boolean") policy.toggleable = settings.toggleable;
  if (settings.params) policy.params = settings.params;
  return policy;
}
