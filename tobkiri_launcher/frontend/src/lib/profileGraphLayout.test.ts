import assert from 'node:assert/strict';
import test from 'node:test';

import type {ApiProfileGraphEdge, ApiProfileGraphNode} from './apiTypes';
import {edgePath, layoutProfileGraph} from './profileGraphLayout';

test('layoutProfileGraph keeps coordinates in a roomy fixed canvas', () => {
  const nodes: ApiProfileGraphNode[] = [
    {id: 'profile:research', kind: 'profile', label: 'Research', ref: 'research', metadata: {}},
    {id: 'tool:web', kind: 'tool', label: 'Web Search', ref: 'web', metadata: {}},
    {id: 'api:messages', kind: 'api', label: 'Messages', ref: 'messages', metadata: {}},
  ];

  const layout = layoutProfileGraph(nodes);

  assert.equal(layout.width >= 1000, true);
  assert.equal(layout.height >= 680, true);
  assert.equal(layout.nodes.some((node) => node.id === 'profile:research'), true);
});

test('edgePath connects node boundaries instead of center points', () => {
  const nodes = layoutProfileGraph([
    {id: 'profile:research', kind: 'profile', label: 'Research', ref: 'research', metadata: {}},
    {id: 'api:messages', kind: 'api', label: 'Messages', ref: 'messages', metadata: {}},
  ]).nodes;
  const positions = new Map(nodes.map((node) => [node.id, node]));
  const profile = positions.get('profile:research')!;
  const edge: ApiProfileGraphEdge = {
    id: 'edge',
    from_id: 'profile:research',
    to_id: 'api:messages',
    kind: 'allows_api',
    active: true,
    metadata: {},
  };

  const path = edgePath(edge, positions);

  assert.match(path, new RegExp(`^M ${profile.x + profile.width} ${profile.y + profile.height / 2} `));
});
