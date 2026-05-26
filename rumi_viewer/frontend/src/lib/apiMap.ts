import type {ApiMapResponseData, ApiMapRuntimePath, ApiProfileGraphEdge, ApiProfileGraphNode} from './apiTypes';

export const API_MAP_NODE_CATEGORY_LABELS = {
  all: 'All',
  entrypoint: 'Entrypoints',
  flow: 'Runtime Flow',
  operation: 'Runtime Units',
  integration: 'Integrations',
  profile: 'Profiles',
  surface: 'Surfaces',
  other: 'Other',
} as const;

export type ApiMapNodeCategory = keyof typeof API_MAP_NODE_CATEGORY_LABELS;

export const API_MAP_NODE_CATEGORIES = Object.keys(API_MAP_NODE_CATEGORY_LABELS) as ApiMapNodeCategory[];

export interface ApiMapDerivedView {
  selectedNode: ApiProfileGraphNode | null;
  nodeById: Map<string, ApiProfileGraphNode>;
  listNodes: ApiProfileGraphNode[];
  visibleNodes: ApiProfileGraphNode[];
  visibleEdges: ApiProfileGraphEdge[];
  inboundEdges: ApiProfileGraphEdge[];
  outboundEdges: ApiProfileGraphEdge[];
  selectedRuntimePath: ApiMapRuntimePath | null;
  connectionGroups: Array<{kind: string; edges: ApiProfileGraphEdge[]}>;
}

export function apiMapNodeCategory(node: ApiProfileGraphNode): Exclude<ApiMapNodeCategory, 'all'> {
  const prefix = node.id.split(':', 1)[0];
  const kind = String(node.kind || '').toLowerCase();
  if (prefix === 'api' || prefix === 'webhook') return 'entrypoint';
  if (prefix === 'flow' || prefix === 'step' || kind === 'flow_step' || kind === 'runtime_choice') return 'flow';
  if (prefix === 'function' || prefix === 'tool' || prefix === 'block' || prefix === 'handler') return 'operation';
  if (kind === 'tool_handler' || kind === 'mcp_server' || kind === 'capability' || kind === 'delivery_action' || kind === 'input_profile') {
    return 'integration';
  }
  if (prefix === 'profile') return 'profile';
  if (prefix === 'prompt' || prefix === 'frontend') return 'surface';
  return 'other';
}

export function countApiMapNodesByCategory(nodes: ApiProfileGraphNode[]): Record<ApiMapNodeCategory, number> {
  const counts = {
    all: nodes.length,
    entrypoint: 0,
    flow: 0,
    operation: 0,
    integration: 0,
    profile: 0,
    surface: 0,
    other: 0,
  } satisfies Record<ApiMapNodeCategory, number>;

  for (const node of nodes) {
    counts[apiMapNodeCategory(node)] += 1;
  }
  return counts;
}

export function filterApiMapNodes(
  nodes: ApiProfileGraphNode[],
  search: string,
  category: ApiMapNodeCategory,
): ApiProfileGraphNode[] {
  const normalizedSearch = search.trim().toLowerCase();
  return [...nodes]
    .filter((node) => category === 'all' || apiMapNodeCategory(node) === category)
    .filter((node) => {
      if (!normalizedSearch) {
        return true;
      }
      const haystack = [
        node.id,
        node.kind,
        node.label,
        node.ref,
        ...Object.values(node.metadata || {}).map((value) => String(value)),
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(normalizedSearch);
    })
    .sort((left, right) => {
      const categoryCompare = API_MAP_NODE_CATEGORIES.indexOf(apiMapNodeCategory(left))
        - API_MAP_NODE_CATEGORIES.indexOf(apiMapNodeCategory(right));
      if (categoryCompare !== 0) {
        return categoryCompare;
      }
      return (left.label || left.ref || left.id).localeCompare(right.label || right.ref || right.id);
    });
}

export function deriveApiMapView(
  data: ApiMapResponseData | null,
  options: {
    selectedNodeId?: string | null;
    search?: string;
    category?: ApiMapNodeCategory;
  },
): ApiMapDerivedView {
  const nodes = data?.nodes || [];
  const edges = data?.edges || [];
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const listNodes = filterApiMapNodes(nodes, options.search || '', options.category || 'all');
  const selectedNode = resolveSelectedNode(nodes, listNodes, options.selectedNodeId);

  if (!selectedNode) {
    return {
      selectedNode: null,
      nodeById,
      listNodes,
      visibleNodes: [],
      visibleEdges: [],
      inboundEdges: [],
      outboundEdges: [],
      selectedRuntimePath: null,
      connectionGroups: [],
    };
  }

  const inboundEdges = edges.filter((edge) => edge.to_id === selectedNode.id);
  const outboundEdges = edges.filter((edge) => edge.from_id === selectedNode.id);
  const neighborhoodIds = new Set<string>([
    selectedNode.id,
    ...inboundEdges.map((edge) => edge.from_id),
    ...outboundEdges.map((edge) => edge.to_id),
  ]);

  return {
    selectedNode,
    nodeById,
    listNodes,
    visibleNodes: nodes.filter((node) => neighborhoodIds.has(node.id)),
    visibleEdges: edges.filter((edge) => neighborhoodIds.has(edge.from_id) && neighborhoodIds.has(edge.to_id)),
    inboundEdges,
    outboundEdges,
    selectedRuntimePath: runtimePathForNode(data, selectedNode.id),
    connectionGroups: groupEdgesByKind([...outboundEdges, ...inboundEdges]),
  };
}

export function edgePeerNodeId(edge: ApiProfileGraphEdge, nodeId: string): string | null {
  if (edge.from_id === nodeId) {
    return edge.to_id;
  }
  if (edge.to_id === nodeId) {
    return edge.from_id;
  }
  return null;
}

export function formatApiMapEdgeKind(kind: string): string {
  return kind.replace(/_/g, ' ');
}

export function apiMapNodeRoleLabel(node: ApiProfileGraphNode): string {
  const kind = String(node.kind || '').toLowerCase();
  const prefix = node.id.split(':', 1)[0];
  if (prefix === 'api') return 'HTTP route';
  if (prefix === 'webhook') return 'Webhook ingress';
  if (prefix === 'flow') return 'Flow';
  if (prefix === 'step' || kind === 'flow_step') return 'Flow step';
  if (prefix === 'function') return 'Operation';
  if (prefix === 'tool') return 'Tool facade';
  if (prefix === 'block') return 'Implementation';
  if (kind === 'handler' || kind === 'tool_handler' || prefix === 'handler') return 'Handler';
  if (kind === 'mcp_server') return 'MCP server';
  if (kind === 'capability') return 'Capability';
  if (kind === 'delivery_action') return 'Delivery';
  if (kind === 'input_profile') return 'Input profile';
  if (prefix === 'profile') return 'Profile policy';
  if (prefix === 'prompt') return 'Prompt';
  if (prefix === 'frontend') return 'Frontend surface';
  return node.kind || 'Runtime entity';
}

export function apiMapNodeRoleDescription(node: ApiProfileGraphNode): string {
  const prefix = node.id.split(':', 1)[0];
  if (prefix === 'function') return 'Stable defaultspack operation boundary used by routes, flows, and tool facades.';
  if (prefix === 'tool') return 'Model-visible facade. It may call a Rumi function, MCP server, capability, or handler.';
  if (prefix === 'block') return 'Internal implementation module behind an operation or legacy route adapter.';
  if (prefix === 'api') return 'HTTP entrypoint matched by defaultspack transport.';
  if (prefix === 'flow') return 'Declarative runtime path executed by FlowEngine.';
  if (prefix === 'step') return 'A FlowEngine step. Function steps converge on defaultspack operations.';
  if (prefix === 'webhook') return 'External ingress endpoint from WebhookEndpointStore.';
  return '';
}

export function runtimePathForNode(data: ApiMapResponseData | null, nodeId?: string | null): ApiMapRuntimePath | null {
  if (!data || !nodeId) {
    return null;
  }
  return (data.runtime_paths || []).find((path) => {
    const nodeIds = [
      path.id,
      path.entrypoint?.node_id,
      path.primary?.node_id,
      path.primary?.block_node_id,
      path.fallback?.node_id,
      path.fallback?.block_node_id,
      ...(path.steps || []).flatMap((step) => [
        step.node_id,
        step.target?.node_id,
        step.target?.block_node_id,
      ]),
    ].filter(Boolean);
    return nodeIds.includes(nodeId);
  }) || null;
}

function groupEdgesByKind(edges: ApiProfileGraphEdge[]): Array<{kind: string; edges: ApiProfileGraphEdge[]}> {
  const groups = new Map<string, ApiProfileGraphEdge[]>();
  for (const edge of edges) {
    const items = groups.get(edge.kind) || [];
    items.push(edge);
    groups.set(edge.kind, items);
  }
  return [...groups.entries()]
    .map(([kind, items]) => ({kind, edges: items}))
    .sort((left, right) => left.kind.localeCompare(right.kind));
}

function resolveSelectedNode(
  nodes: ApiProfileGraphNode[],
  filteredNodes: ApiProfileGraphNode[],
  selectedNodeId?: string | null,
): ApiProfileGraphNode | null {
  if (selectedNodeId) {
    const selected = nodes.find((node) => node.id === selectedNodeId);
    if (selected) {
      return selected;
    }
  }
  return filteredNodes[0] || nodes[0] || null;
}
