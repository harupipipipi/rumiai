import type {
  ApiAiInputConfig,
  ApiAiInputEdge,
  ApiPromptSegment,
  StartupProfileAiInputResponseData,
} from '@/src/lib/apiTypes';

export function normalizeAiInputConfig(config?: Partial<ApiAiInputConfig> | null): ApiAiInputConfig {
  return {
    version: Number(config?.version || 1),
    disabled_edges: Array.isArray(config?.disabled_edges)
      ? uniqueStrings(config.disabled_edges)
      : [],
    gates: recordOfRecords(config?.gates),
    inserted_edges: Array.isArray(config?.inserted_edges)
      ? config.inserted_edges.filter(isAiInputEdge)
      : [],
    budgets: recordOfRecords(config?.budgets),
  };
}

export function toggleAiInputEdge(config: ApiAiInputConfig, edgeId: string, disabled: boolean): ApiAiInputConfig {
  const normalized = normalizeAiInputConfig(config);
  const current = new Set(normalized.disabled_edges);
  if (disabled) {
    current.add(edgeId);
  } else {
    current.delete(edgeId);
  }
  return {
    ...normalized,
    disabled_edges: Array.from(current).sort(),
  };
}

export function insertConditionGate(
  config: ApiAiInputConfig,
  edge: ApiAiInputEdge,
  expression: {field: string; op: string; value: string},
): ApiAiInputConfig {
  const normalized = normalizeAiInputConfig(config);
  const field = expression.field.trim() || 'message';
  const op = expression.op.trim() || 'contains';
  const value = expression.value.trim();
  const gateId = uniqueGateId(normalized, edge, field, op, value);
  const toPort = edge.to_port || 'system';
  const firstEdge: ApiAiInputEdge = {
    id: `edge:${edge.from_id}->${gateId}.input`,
    from_id: edge.from_id,
    from_port: edge.from_port || 'output',
    to_id: gateId,
    to_port: 'input',
    kind: edge.kind || 'contributes_to',
    active: true,
    gate_id: null,
    metadata: {
      inserted_by: 'ai_input_inspector',
      replaces_edge: edge.id,
    },
  };
  const secondEdge: ApiAiInputEdge = {
    id: `edge:${gateId}->${edge.to_id}.${toPort}`,
    from_id: gateId,
    from_port: 'pass',
    to_id: edge.to_id,
    to_port: toPort,
    kind: 'gates',
    active: true,
    gate_id: gateId,
    metadata: {
      inserted_by: 'ai_input_inspector',
      replaces_edge: edge.id,
    },
  };

  return {
    ...toggleAiInputEdge(normalized, edge.id, true),
    gates: {
      ...normalized.gates,
      [gateId]: {
        id: gateId,
        kind: 'condition_gate',
        label: `Condition for ${edge.from_id}`,
        expression: {field, op, value},
        default: false,
      },
    },
    inserted_edges: upsertEdges(normalized.inserted_edges, [firstEdge, secondEdge]),
  };
}

export function aiInputHeavyNodes(
  data: StartupProfileAiInputResponseData | null,
  limit = 12,
): Array<{id: string; tokens: number}> {
  const entries = Object.entries(data?.token_estimate.by_node || {});
  return entries
    .map(([id, tokens]) => ({id, tokens: Number(tokens || 0)}))
    .sort((left, right) => right.tokens - left.tokens)
    .slice(0, limit);
}

export function aiInputEffectiveToolIds(data: StartupProfileAiInputResponseData | null): string[] {
  return (data?.effective_input.tool_schemas || [])
    .map((segment) => segment.tool_id || segment.name)
    .filter((value): value is string => Boolean(value));
}

export function aiInputPolicySegments(data: StartupProfileAiInputResponseData | null): ApiPromptSegment[] {
  const policy = data?.effective_input.policy;
  if (!isRecord(policy) || !Array.isArray(policy.segments)) {
    return [];
  }
  return policy.segments.filter(isPromptSegment);
}

function uniqueStrings(value: unknown[]): string[] {
  return Array.from(new Set(value.map((item) => String(item || '').trim()).filter(Boolean))).sort();
}

function uniqueGateId(
  config: ApiAiInputConfig,
  edge: ApiAiInputEdge,
  field: string,
  op: string,
  value: string,
): string {
  const base = `gate:${slugify(`${edge.from_id}-${field}-${op}-${value || 'value'}`)}`;
  let candidate = base;
  let suffix = 2;
  while (config.gates[candidate]) {
    candidate = `${base}-${suffix}`;
    suffix += 1;
  }
  return candidate;
}

function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9:_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
  return slug || 'condition';
}

function upsertEdges(current: ApiAiInputEdge[], nextEdges: ApiAiInputEdge[]): ApiAiInputEdge[] {
  const byId = new Map<string, ApiAiInputEdge>();
  for (const edge of current) {
    byId.set(edge.id, edge);
  }
  for (const edge of nextEdges) {
    byId.set(edge.id, edge);
  }
  return Array.from(byId.values()).sort((left, right) => left.id.localeCompare(right.id));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isPromptSegment(value: unknown): value is ApiPromptSegment {
  if (!isRecord(value)) {
    return false;
  }
  return typeof value.id === 'string'
    && typeof value.source === 'string'
    && typeof value.source_type === 'string'
    && typeof value.tokens === 'number';
}

function recordOfRecords(value: unknown): Record<string, Record<string, unknown>> {
  if (!isRecord(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, Record<string, unknown>] => isRecord(entry[1])),
  );
}

function isAiInputEdge(value: unknown): value is ApiAiInputEdge {
  if (!isRecord(value)) {
    return false;
  }
  return typeof value.id === 'string'
    && typeof value.from_id === 'string'
    && typeof value.to_id === 'string'
    && typeof value.kind === 'string';
}
