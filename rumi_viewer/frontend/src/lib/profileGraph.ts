import type {
  ApiProfileGraphAvailableItem,
  ApiProfileGraphDocument,
  ApiProfileGraphEdge,
  ApiProfileGraphNode,
  ApiProfileGraphSelected,
} from './apiTypes';

export const PROFILE_GRAPH_CATEGORY_LABELS = {
  tools: '+ Tool',
  webhooks: '+ Webhook',
  api_routes: '+ API',
  prompts: '+ Prompt',
  frontend: '+ Frontend',
  flows: '+ Flow',
  nodes: '+ Node',
} as const;

export const PROFILE_GRAPH_CATEGORIES = Object.keys(PROFILE_GRAPH_CATEGORY_LABELS) as ProfileGraphCategory[];

export type ProfileGraphCategory = keyof typeof PROFILE_GRAPH_CATEGORY_LABELS;

const CATEGORY_META: Record<ProfileGraphCategory, { prefix: string; edgeKind: string; fallbackKind: string }> = {
  tools: { prefix: 'tool', edgeKind: 'selects', fallbackKind: 'tool' },
  webhooks: { prefix: 'webhook', edgeKind: 'receives_from', fallbackKind: 'webhook' },
  api_routes: { prefix: 'api', edgeKind: 'allows_api', fallbackKind: 'api' },
  prompts: { prefix: 'prompt', edgeKind: 'uses_prompt', fallbackKind: 'prompt' },
  frontend: { prefix: 'frontend', edgeKind: 'uses_frontend', fallbackKind: 'frontend' },
  flows: { prefix: 'flow', edgeKind: 'launches_flow', fallbackKind: 'flow' },
  nodes: { prefix: 'node', edgeKind: 'uses_node', fallbackKind: 'node' },
};

export function profileGraphNodePrefix(category: ProfileGraphCategory): string {
  return CATEGORY_META[category].prefix;
}

export function normalizeProfileGraphSelected(
  selected?: Partial<ApiProfileGraphSelected> | null,
): ApiProfileGraphSelected {
  const normalized = {} as ApiProfileGraphSelected;
  for (const category of PROFILE_GRAPH_CATEGORIES) {
    normalized[category] = normalizeStringList(selected?.[category]);
  }
  return normalized;
}

export function normalizeProfileGraphDocument(
  profileId: string,
  graph?: Partial<ApiProfileGraphDocument> | null,
): ApiProfileGraphDocument {
  const selected = normalizeProfileGraphSelected(graph?.selected);
  const nodes = Array.isArray(graph?.nodes) ? [...graph.nodes] : [];
  const edges = Array.isArray(graph?.edges) ? [...graph.edges] : [];
  const profileNode = ensureProfileNode(nodes, profileId);

  return {
    version: Number(graph?.version || 1),
    profile_id: profileId,
    nodes: dedupeNodes([...nodes.filter((node) => node.id !== profileNode.id), profileNode]),
    edges: dedupeEdges(edges),
    selected,
  };
}

export function profileGraphRequestPayload(document: ApiProfileGraphDocument): {
  graph: Pick<ApiProfileGraphDocument, 'version' | 'nodes' | 'edges'>;
  selected: ApiProfileGraphSelected;
} {
  return {
    graph: {
      version: document.version,
      nodes: document.nodes,
      edges: document.edges,
    },
    selected: document.selected,
  };
}

export function addProfileGraphSelection(
  document: ApiProfileGraphDocument,
  category: ProfileGraphCategory,
  item: Pick<ApiProfileGraphAvailableItem, 'id' | 'label' | 'kind'> & Record<string, unknown>,
): ApiProfileGraphDocument {
  const selected = normalizeProfileGraphSelected(document.selected);
  const profileNode = ensureProfileNode(document.nodes, document.profile_id);
  const meta = CATEGORY_META[category];
  const ref = String(item.id || '').trim();
  if (!ref) {
    return normalizeProfileGraphDocument(document.profile_id, document);
  }
  const nextSelected = {
    ...selected,
    [category]: normalizeStringList([...(selected[category] || []), ref]),
  };
  const nodeId = `${meta.prefix}:${ref}`;
  const nextNode: ApiProfileGraphNode = {
    id: nodeId,
    kind: String(item.kind || meta.fallbackKind),
    label: String(item.label || ref),
    ref,
    metadata: {...item},
  };
  const nextEdge: ApiProfileGraphEdge = {
    id: `${profileNode.id}->${nodeId}:${meta.edgeKind}`,
    from_id: profileNode.id,
    to_id: nodeId,
    kind: meta.edgeKind,
    active: true,
    metadata: {selected_ref: ref},
  };

  return normalizeProfileGraphDocument(document.profile_id, {
    ...document,
    selected: nextSelected,
    nodes: dedupeNodes([...document.nodes, profileNode, nextNode]),
    edges: dedupeEdges([...document.edges, nextEdge]),
  });
}

export function removeProfileGraphSelection(
  document: ApiProfileGraphDocument,
  category: ProfileGraphCategory,
  ref: string,
): ApiProfileGraphDocument {
  const meta = CATEGORY_META[category];
  const normalizedRef = String(ref || '').trim();
  const nodeId = `${meta.prefix}:${normalizedRef}`;
  const selected = normalizeProfileGraphSelected(document.selected);
  const nextSelected = {
    ...selected,
    [category]: selected[category].filter((value) => value !== normalizedRef),
  };

  const remainingEdges = document.edges.filter((edge) => {
    if (edge.to_id === nodeId && edge.kind === meta.edgeKind) {
      return false;
    }
    return edge.from_id !== nodeId && edge.to_id !== nodeId;
  });

  const stillReferenced = new Set<string>();
  for (const edge of remainingEdges) {
    stillReferenced.add(edge.from_id);
    stillReferenced.add(edge.to_id);
  }

  const remainingNodes = document.nodes.filter((node) => {
    if (node.id === nodeId) {
      return false;
    }
    if (node.id === `profile:${document.profile_id}`) {
      return true;
    }
    return stillReferenced.has(node.id) || !node.id.includes(':');
  });

  return normalizeProfileGraphDocument(document.profile_id, {
    ...document,
    selected: nextSelected,
    nodes: remainingNodes,
    edges: remainingEdges,
  });
}

export function graphNodeKindLabel(node: Pick<ApiProfileGraphNode, 'id' | 'kind'>): string {
  const prefix = node.id.split(':', 1)[0];
  if (prefix === 'api') return 'API Route';
  if (prefix === 'tool') return 'Tool';
  if (prefix === 'webhook') return 'Webhook';
  if (prefix === 'prompt') return 'Prompt';
  if (prefix === 'frontend') return 'Frontend';
  if (prefix === 'flow') return node.kind === 'capability_graph' ? 'Capability Graph' : 'Flow';
  if (prefix === 'profile') return 'Profile';
  if (prefix === 'node') return 'Node';
  return node.kind;
}

export function categoryForGraphNodeId(nodeId: string): ProfileGraphCategory | null {
  const prefix = nodeId.split(':', 1)[0];
  for (const [category, meta] of Object.entries(CATEGORY_META) as Array<[ProfileGraphCategory, typeof CATEGORY_META[ProfileGraphCategory]]>) {
    if (meta.prefix === prefix) {
      return category;
    }
  }
  return null;
}

export function normalizeStringList(value: unknown): string[] {
  if (typeof value === 'string') {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (!Array.isArray(value)) {
    return [];
  }
  const seen = new Set<string>();
  const result: string[] = [];
  for (const entry of value) {
    const normalized = String(entry || '').trim();
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
}

function ensureProfileNode(nodes: ApiProfileGraphNode[], profileId: string): ApiProfileGraphNode {
  const existing = nodes.find((node) => node.id === `profile:${profileId}`);
  if (existing) {
    return existing;
  }
  return {
    id: `profile:${profileId}`,
    kind: 'profile',
    label: profileId,
    ref: profileId,
    metadata: {profile_id: profileId},
  };
}

function dedupeNodes(nodes: ApiProfileGraphNode[]): ApiProfileGraphNode[] {
  const byId = new Map<string, ApiProfileGraphNode>();
  for (const node of nodes) {
    byId.set(node.id, node);
  }
  return [...byId.values()];
}

function dedupeEdges(edges: ApiProfileGraphEdge[]): ApiProfileGraphEdge[] {
  const byId = new Map<string, ApiProfileGraphEdge>();
  for (const edge of edges) {
    byId.set(edge.id, edge);
  }
  return [...byId.values()];
}
