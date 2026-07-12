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
  profile: {x: 500, y: 320},
  prompt: {x: 500, y: 92},
  tool: {x: 170, y: 180},
  webhook: {x: 170, y: 420},
  api: {x: 830, y: 180},
  frontend: {x: 830, y: 420},
  flow: {x: 650, y: 588},
  node: {x: 350, y: 588},
  storage: {x: 500, y: 540},
};

const ROW_GAP = 96;
const COLUMN_GAP = 184;
const ROWS_PER_GROUP = 3;
const CANVAS_PADDING = 80;

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
        const row = index % ROWS_PER_GROUP;
        const column = Math.floor(index / ROWS_PER_GROUP);
        const width = group === 'profile' ? 180 : group === 'storage' ? 148 : 156;
        const height = group === 'storage' ? 56 : 70;
        positioned.push({
          ...node,
          x: anchor.x + column * COLUMN_GAP - width / 2,
          y: anchor.y + row * ROW_GAP - height / 2,
          width,
          height,
        });
      });
  }

  const maxX = Math.max(...positioned.map((node) => node.x + node.width), 0);
  const maxY = Math.max(...positioned.map((node) => node.y + node.height), 0);

  return {
    nodes: positioned,
    width: Math.max(1000, maxX + CANVAS_PADDING),
    height: Math.max(680, maxY + CANVAS_PADDING),
  };
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
  const fromCenter = centerPoint(from);
  const toCenter = centerPoint(to);
  const horizontal = Math.abs(toCenter.x - fromCenter.x) >= Math.abs(toCenter.y - fromCenter.y);
  const start = boundaryPoint(from, toCenter, horizontal);
  const end = boundaryPoint(to, fromCenter, horizontal);

  if (horizontal) {
    const midX = (start.x + end.x) / 2;
    return `M ${start.x} ${start.y} C ${midX} ${start.y}, ${midX} ${end.y}, ${end.x} ${end.y}`;
  }

  const midY = (start.y + end.y) / 2;
  return `M ${start.x} ${start.y} C ${start.x} ${midY}, ${end.x} ${midY}, ${end.x} ${end.y}`;
}

function centerPoint(node: PositionedProfileGraphNode): {x: number; y: number} {
  return {
    x: node.x + node.width / 2,
    y: node.y + node.height / 2,
  };
}

function boundaryPoint(
  node: PositionedProfileGraphNode,
  target: {x: number; y: number},
  preferHorizontal: boolean,
): {x: number; y: number} {
  const center = centerPoint(node);

  if (preferHorizontal) {
    return {
      x: target.x >= center.x ? node.x + node.width : node.x,
      y: center.y,
    };
  }

  return {
    x: center.x,
    y: target.y >= center.y ? node.y + node.height : node.y,
  };
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
