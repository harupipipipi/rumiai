import type {ApiProfileGraphEdge, ApiProfileGraphNode} from './apiTypes';

export interface PositionedProfileGraphNode extends ApiProfileGraphNode {
  x: number;
  y: number;
  width: number;
  height: number;
}

const GROUP_ORDER = [
  'profile',
  'prompt',
  'tool',
  'webhook',
  'api',
  'frontend',
  'flow',
  'node',
  'storage',
] as const;

const GROUP_ANCHORS: Record<(typeof GROUP_ORDER)[number], {x: number; y: number}> = {
  profile: {x: 360, y: 250},
  prompt: {x: 360, y: 60},
  tool: {x: 90, y: 120},
  webhook: {x: 90, y: 320},
  api: {x: 630, y: 120},
  frontend: {x: 630, y: 320},
  flow: {x: 520, y: 430},
  node: {x: 210, y: 430},
  storage: {x: 360, y: 430},
};

export function layoutProfileGraph(
  nodes: ApiProfileGraphNode[],
): {nodes: PositionedProfileGraphNode[]; width: number; height: number} {
  const groups = new Map<(typeof GROUP_ORDER)[number], ApiProfileGraphNode[]>();
  for (const group of GROUP_ORDER) {
    groups.set(group, []);
  }

  for (const node of nodes) {
    groups.get(groupForNode(node))?.push(node);
  }

  const positioned: PositionedProfileGraphNode[] = [];
  for (const group of GROUP_ORDER) {
    const items = groups.get(group) || [];
    const anchor = GROUP_ANCHORS[group];
    items
      .sort((left, right) => (left.label || left.ref || left.id).localeCompare(right.label || right.ref || right.id))
      .forEach((node, index) => {
        const row = index % 3;
        const column = Math.floor(index / 3);
        const width = group === 'profile' ? 170 : group === 'storage' ? 132 : 148;
        const height = group === 'storage' ? 52 : 72;
        positioned.push({
          ...node,
          x: anchor.x + column * 160 - width / 2,
          y: anchor.y + row * 84 - height / 2,
          width,
          height,
        });
      });
  }

  return {nodes: positioned, width: 760, height: 520};
}

export function edgePath(
  edge: ApiProfileGraphEdge,
  positions: Map<string, PositionedProfileGraphNode>,
): string {
  const from = positions.get(edge.from_id);
  const to = positions.get(edge.to_id);
  if (!from || !to) {
    return '';
  }
  const startX = from.x + from.width / 2;
  const startY = from.y + from.height / 2;
  const endX = to.x + to.width / 2;
  const endY = to.y + to.height / 2;
  const midX = (startX + endX) / 2;
  return `M ${startX} ${startY} C ${midX} ${startY}, ${midX} ${endY}, ${endX} ${endY}`;
}

function groupForNode(node: ApiProfileGraphNode): (typeof GROUP_ORDER)[number] {
  const prefix = node.id.split(':', 1)[0];
  if (prefix === 'profile') return 'profile';
  if (prefix === 'prompt') return 'prompt';
  if (prefix === 'tool') return 'tool';
  if (prefix === 'webhook') return 'webhook';
  if (prefix === 'api') return 'api';
  if (prefix === 'frontend') return 'frontend';
  if (prefix === 'flow') return 'flow';
  if (prefix === 'storage') return 'storage';
  if (prefix === 'node' && node.kind === 'storage') return 'storage';
  return 'node';
}
