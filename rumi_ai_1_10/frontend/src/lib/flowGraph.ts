import type { Connection, Edge, Node } from '@xyflow/react';
import type {
  FlowDocumentMeta,
  FlowPort,
  PortDirection,
  StepNodeData,
  TriggerNodeData,
} from './types';

export const DEFAULT_BASE_PACK = 'basepack';
export const DEFAULT_GRAPH_PHASE = 'graph';
export const DEFAULT_START_NODE_ID = 'node-rumi-start';
export const DEFAULT_END_NODE_ID = 'node-rumi-end';

export interface ConnectionValidationResult {
  valid: boolean;
  reason?: string;
}

export function normalizeContracts(input: string[] | string | undefined): string[] {
  if (!input) {
    return [];
  }
  const raw = Array.isArray(input) ? input : input.split(',');
  return Array.from(
    new Set(
      raw
        .map((value) => value.trim())
        .filter(Boolean),
    ),
  );
}

export function createPort(
  label: string,
  direction: PortDirection,
  contracts: string[] = [],
  overrides: Partial<FlowPort> = {},
): FlowPort {
  const normalizedLabel = label.trim() || (direction === 'input' ? 'input' : 'output');
  const id = overrides.id?.trim() || `${direction}-${normalizedLabel.toLowerCase().replace(/[^a-z0-9]+/gi, '-')}`;
  return {
    id,
    label: normalizedLabel,
    direction,
    contracts: normalizeContracts(overrides.contracts ?? contracts),
    description: overrides.description,
    allowMultiple: overrides.allowMultiple ?? false,
  };
}

export function ensureUniquePortId(candidateId: string, ports: FlowPort[], excludedId?: string): string {
  const baseId = candidateId.trim() || 'port';
  const takenIds = new Set(
    ports
      .filter((port) => port.id !== excludedId)
      .map((port) => port.id),
  );

  if (!takenIds.has(baseId)) {
    return baseId;
  }

  let suffix = 2;
  let nextId = `${baseId}-${suffix}`;
  while (takenIds.has(nextId)) {
    suffix += 1;
    nextId = `${baseId}-${suffix}`;
  }
  return nextId;
}

export function createUniquePort(
  label: string,
  direction: PortDirection,
  contracts: string[] = [],
  existingPorts: FlowPort[] = [],
  overrides: Partial<FlowPort> = {},
): FlowPort {
  const nextPort = createPort(label, direction, contracts, overrides);
  return {
    ...nextPort,
    id: ensureUniquePortId(nextPort.id, existingPorts),
  };
}

export function clonePorts(ports: FlowPort[] | undefined): FlowPort[] {
  return (ports ?? []).map((port) => ({
    ...port,
    contracts: [...port.contracts],
  }));
}

export function getNodePorts(node: Node | null | undefined, direction?: PortDirection): FlowPort[] {
  const ports = clonePorts((node?.data as { ports?: FlowPort[] } | undefined)?.ports);
  if (!direction) {
    return ports;
  }
  return ports.filter((port) => port.direction === direction);
}

export function getPort(node: Node | null | undefined, handleId: string | null | undefined): FlowPort | null {
  const ports = getNodePorts(node);
  if (handleId) {
    return ports.find((port) => port.id === handleId) ?? null;
  }
  return ports[0] ?? null;
}

export function replaceNodePorts(nodes: Node[], nodeId: string, ports: FlowPort[]): Node[] {
  return nodes.map((node) => (
    node.id === nodeId
      ? { ...node, data: { ...node.data, ports } }
      : node
  ));
}

function hasContractMatch(sourcePort: FlowPort | null, targetPort: FlowPort | null): boolean {
  if (!sourcePort || !targetPort) {
    return false;
  }
  if (sourcePort.contracts.length === 0 || targetPort.contracts.length === 0) {
    return true;
  }
  return sourcePort.contracts.some((contract) => targetPort.contracts.includes(contract));
}

function portConnectionCount(edges: Edge[], nodeId: string, handleId: string | null | undefined, direction: PortDirection): number {
  return edges.filter((edge) =>
    direction === 'output'
      ? edge.source === nodeId && (handleId ? edge.sourceHandle === handleId : !edge.sourceHandle)
      : edge.target === nodeId && (handleId ? edge.targetHandle === handleId : !edge.targetHandle),
  ).length;
}

export function validateConnection(
  connection: Connection | Edge,
  nodes: Node[],
  edges: Edge[],
): ConnectionValidationResult {
  if (!connection.source || !connection.target) {
    return { valid: false, reason: '接続先が不完全です。' };
  }
  if (connection.source === connection.target) {
    return { valid: false, reason: '同じノード同士は接続できません。' };
  }

  const sourceNode = nodes.find((node) => node.id === connection.source) ?? null;
  const targetNode = nodes.find((node) => node.id === connection.target) ?? null;

  if (!sourceNode || !targetNode) {
    return { valid: false, reason: '接続対象ノードが見つかりません。' };
  }

  const sourcePort = getPort(sourceNode, connection.sourceHandle);
  const targetPort = getPort(targetNode, connection.targetHandle);

  if (!sourcePort || sourcePort.direction !== 'output') {
    return { valid: false, reason: '出力ポートから接続してください。' };
  }
  if (!targetPort || targetPort.direction !== 'input') {
    return { valid: false, reason: '入力ポートに接続してください。' };
  }

  if (!hasContractMatch(sourcePort, targetPort)) {
    return {
      valid: false,
      reason: `ポート規格が一致しません: ${sourcePort.label} -> ${targetPort.label}`,
    };
  }

  if (!sourcePort.allowMultiple && portConnectionCount(edges, connection.source, sourcePort.id, 'output') > 0) {
    return { valid: false, reason: `${sourcePort.label} は複数接続を許可していません。` };
  }
  if (!targetPort.allowMultiple && portConnectionCount(edges, connection.target, targetPort.id, 'input') > 0) {
    return { valid: false, reason: `${targetPort.label} は複数接続を許可していません。` };
  }

  return { valid: true };
}

export function pickCompatibleHandles(
  sourceNode: Node,
  targetNode: Node,
  edges: Edge[],
): { sourceHandle: string | null; targetHandle: string | null } | null {
  const sourcePorts = getNodePorts(sourceNode, 'output');
  const targetPorts = getNodePorts(targetNode, 'input');

  for (const sourcePort of sourcePorts) {
    for (const targetPort of targetPorts) {
      const result = validateConnection(
        {
          source: sourceNode.id,
          target: targetNode.id,
          sourceHandle: sourcePort.id,
          targetHandle: targetPort.id,
        },
        [sourceNode, targetNode],
        edges,
      );
      if (result.valid) {
        return {
          sourceHandle: sourcePort.id,
          targetHandle: targetPort.id,
        };
      }
    }
  }

  return null;
}

export function syncEdgesForUpdatedPort(
  edges: Edge[],
  nodes: Node[],
  nodeId: string,
  previousPortId: string,
  nextPortId: string,
): Edge[] {
  const remappedEdges = edges.map((edge) => {
    if (edge.source === nodeId && edge.sourceHandle === previousPortId) {
      return {
        ...edge,
        sourceHandle: nextPortId,
      };
    }
    if (edge.target === nodeId && edge.targetHandle === previousPortId) {
      return {
        ...edge,
        targetHandle: nextPortId,
      };
    }
    return edge;
  });

  return remappedEdges.filter((edge) => {
    const otherEdges = remappedEdges.filter((candidate) => candidate.id !== edge.id);
    return validateConnection(edge, nodes, otherEdges).valid;
  });
}

export function removeEdgesForPort(edges: Edge[], nodeId: string, portId: string): Edge[] {
  return edges.filter((edge) => (
    !(edge.source === nodeId && edge.sourceHandle === portId)
    && !(edge.target === nodeId && edge.targetHandle === portId)
  ));
}

export function createStartNode(position = { x: 160, y: 120 }, basePack = DEFAULT_BASE_PACK): Node<TriggerNodeData> {
  return {
    id: DEFAULT_START_NODE_ID,
    type: 'trigger',
    position,
    data: {
      type: 'rumi_start',
      title: 'rumi_start',
      basePack,
      ports: [
        createPort('起動', 'output', ['flow.start'], {
          id: 'start-out',
          allowMultiple: true,
          description: '起動時に downstream へ流すベースポート。',
        }),
      ],
    },
  };
}

export function createEndNode(position = { x: 920, y: 320 }): Node {
  return {
    id: DEFAULT_END_NODE_ID,
    type: 'end',
    position,
    data: {
      title: 'finish',
      ports: [
        createPort('完了', 'input', [], {
          id: 'end-in',
          allowMultiple: true,
        }),
      ],
    },
  };
}

export function createStepNode(
  step: {
    id: string;
    type?: string;
    title?: string;
    description?: string;
    ports?: FlowPort[];
    phase?: string;
    inputs?: Record<string, unknown>;
  },
  position: { x: number; y: number },
): Node<StepNodeData> {
  return {
    id: `node-${step.id}-${Date.now()}`,
    type: 'step',
    position,
    data: {
      id: step.id,
      type: step.type ?? 'action',
      title: step.title ?? step.id,
      description: step.description,
      phase: step.phase ?? DEFAULT_GRAPH_PHASE,
      inputs: step.inputs ?? {},
      ports: clonePorts(step.ports?.length ? step.ports : defaultPortsForStep(step.id)),
    },
  };
}

export function defaultPortsForStep(stepId: string): FlowPort[] {
  const presets: Record<string, FlowPort[]> = {
    'mounts.init': [
      createPort('起動', 'input', ['flow.start'], { id: 'boot-in' }),
      createPort('mounts', 'output', ['mounts.ready'], { id: 'mounts-out' }),
    ],
    'registry.load': [
      createPort('mounts', 'input', ['mounts.ready'], { id: 'mounts-in' }),
      createPort('registry', 'output', ['registry.ready'], { id: 'registry-out' }),
    ],
    'check_profile': [
      createPort('起動', 'input', ['flow.start'], { id: 'profile-in' }),
      createPort('profile', 'output', ['profile.ready'], { id: 'profile-out' }),
    ],
    emit: [
      createPort('event', 'input', ['event.any'], { id: 'event-in' }),
      createPort('signal', 'output', ['event.any'], { id: 'event-out', allowMultiple: true }),
    ],
    'exec_py': [
      createPort('command', 'input', ['command.python'], { id: 'exec-in' }),
      createPort('result', 'output', ['data.python'], { id: 'exec-out' }),
    ],
    'http.get': [
      createPort('request', 'input', ['http.request'], { id: 'http-in' }),
      createPort('response', 'output', ['http.response'], { id: 'http-out' }),
    ],
    'http.post': [
      createPort('request', 'input', ['http.request'], { id: 'http-post-in' }),
      createPort('response', 'output', ['http.response'], { id: 'http-post-out' }),
    ],
    'log.info': [
      createPort('text', 'input', ['text.plain'], { id: 'log-in', allowMultiple: true }),
      createPort('signal', 'output', ['event.any'], { id: 'log-out', allowMultiple: true }),
    ],
  };

  return clonePorts(
    presets[stepId] ?? [
      createPort('input', 'input', [], { id: 'input-main' }),
      createPort('output', 'output', [], { id: 'output-main', allowMultiple: true }),
    ],
  );
}

export function createDefaultFlowGraph(basePack = DEFAULT_BASE_PACK): { nodes: Node[]; edges: Edge[]; meta: FlowDocumentMeta } {
  const start = createStartNode({ x: 140, y: 140 }, basePack);
  const end = createEndNode({ x: 880, y: 180 });

  return {
    nodes: [start, end],
    edges: [],
    meta: {
      flowId: 'untitled',
      phases: [DEFAULT_GRAPH_PHASE],
      defaults: {
        fail_soft: true,
        on_missing_step: 'skip',
      },
      basePack,
    },
  };
}

export function sanitizeNode(node: Node): Node {
  return {
    ...node,
    data: {
      ...node.data,
      ports: clonePorts((node.data as { ports?: FlowPort[] }).ports),
      executionStatus: undefined,
    },
  };
}

export function buildExecutionPlan(nodes: Node[], edges: Edge[]): Node[] {
  const startNode = nodes.find((node) => node.type === 'trigger');
  if (!startNode) {
    return nodes.filter((node) => node.type === 'step');
  }

  const plan: Node[] = [];
  const visited = new Set<string>([startNode.id]);
  const queue = [startNode.id];

  while (queue.length > 0) {
    const current = queue.shift();
    if (!current) {
      continue;
    }
    const outgoing = edges
      .filter((edge) => edge.source === current)
      .map((edge) => nodes.find((node) => node.id === edge.target))
      .filter((node): node is Node => Boolean(node));

    for (const next of outgoing) {
      if (visited.has(next.id)) {
        continue;
      }
      visited.add(next.id);
      queue.push(next.id);
      if (next.type === 'step') {
        plan.push(next);
      }
    }
  }

  return plan;
}
