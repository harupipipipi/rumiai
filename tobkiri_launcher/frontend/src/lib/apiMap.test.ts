import assert from 'node:assert/strict';
import test from 'node:test';

import type {ApiMapResponseData} from './apiTypes';
import {
  apiMapNodeRoleDescription,
  apiMapNodeRoleLabel,
  countApiMapNodesByCategory,
  deriveApiMapView,
  filterApiMapNodes,
  runtimePathForNode,
} from './apiMap';

function sampleApiMap(): ApiMapResponseData {
  return {
    nodes: [
      {id: 'profile:default-profile', kind: 'profile', label: 'Default Profile', ref: 'default-profile', metadata: {}},
      {id: 'tool:web_search', kind: 'tool', label: 'Web Search', ref: 'web_search', metadata: {}},
      {id: 'api:POST /api/chat', kind: 'api', label: 'POST /api/chat', ref: 'POST /api/chat', metadata: {}},
      {id: 'block:chat.handler', kind: 'block', label: 'chat.handler', ref: 'chat.handler', metadata: {}},
      {id: 'webhook:research-webhook', kind: 'webhook', label: 'Research Webhook', ref: 'research-webhook', metadata: {}},
    ],
    edges: [
      {id: 'profile:default-profile->tool:web_search:selects', from_id: 'profile:default-profile', to_id: 'tool:web_search', kind: 'selects', active: true, metadata: {}},
      {id: 'profile:default-profile->api:POST /api/chat:allows_api', from_id: 'profile:default-profile', to_id: 'api:POST /api/chat', kind: 'allows_api', active: true, metadata: {}},
      {id: 'api:POST /api/chat->block:chat.handler:handled_by', from_id: 'api:POST /api/chat', to_id: 'block:chat.handler', kind: 'handled_by', active: true, metadata: {}},
      {id: 'webhook:research-webhook->profile:default-profile:receives_from', from_id: 'webhook:research-webhook', to_id: 'profile:default-profile', kind: 'receives_from', active: true, metadata: {}},
    ],
    runtime_paths: [
      {
        id: 'api:POST /api/chat',
        label: 'POST /api/chat',
        entrypoint: {node_id: 'api:POST /api/chat', method: 'POST', path: '/api/chat', source: 'flow_yaml_or_registry', source_type: 'flow'},
        primary: {kind: 'flow', id: 'chat.flow', node_id: 'flow:chat.flow'},
        fallback: {kind: 'block', id: 'chat.handler', node_id: 'block:chat.handler'},
        steps: [
          {id: 'load_profile', node_id: 'step:chat.flow:load_profile', step_type: 'function', order: 1, target: {kind: 'function', id: 'defaultspack:profile_load_active', node_id: 'function:defaultspack:profile_load_active'}},
        ],
      },
    ],
    profile_runtime: {},
    summary: {
      node_count: 5,
      edge_count: 4,
      route_count: 1,
      tool_count: 1,
      webhook_count: 1,
    },
    diagnostics: [],
  };
}

test('deriveApiMapView returns a focused neighborhood around the selected node', () => {
  const view = deriveApiMapView(sampleApiMap(), {
    selectedNodeId: 'profile:default-profile',
    search: '',
    category: 'all',
  });

  assert.equal(view.selectedNode?.id, 'profile:default-profile');
  assert.deepEqual(
    view.visibleNodes.map((node) => node.id).sort(),
    ['api:POST /api/chat', 'profile:default-profile', 'tool:web_search', 'webhook:research-webhook'],
  );
  assert.equal(view.inboundEdges.length, 1);
  assert.equal(view.outboundEdges.length, 2);
});

test('filterApiMapNodes narrows the node directory by category and search', () => {
  const nodes = sampleApiMap().nodes;

  assert.deepEqual(
    filterApiMapNodes(nodes, 'chat', 'entrypoint').map((node) => node.id),
    ['api:POST /api/chat'],
  );
  assert.deepEqual(
    filterApiMapNodes(nodes, 'research', 'entrypoint').map((node) => node.id),
    ['webhook:research-webhook'],
  );
  assert.deepEqual(
    filterApiMapNodes(nodes, 'web', 'operation').map((node) => node.id),
    ['tool:web_search'],
  );
});

test('countApiMapNodesByCategory reports top-level category totals', () => {
  const counts = countApiMapNodesByCategory(sampleApiMap().nodes);

  assert.equal(counts.all, 5);
  assert.equal(counts.profile, 1);
  assert.equal(counts.entrypoint, 2);
  assert.equal(counts.operation, 2);
  assert.equal(counts.other, 0);
});

test('runtimePathForNode resolves routes and flow step targets', () => {
  const map = sampleApiMap();

  assert.equal(runtimePathForNode(map, 'api:POST /api/chat')?.label, 'POST /api/chat');
  assert.equal(runtimePathForNode(map, 'function:defaultspack:profile_load_active')?.label, 'POST /api/chat');
  assert.equal(runtimePathForNode(map, 'tool:web_search'), null);
});

test('api map role labels collapse functions, tools, and blocks into operation semantics', () => {
  const nodes = sampleApiMap().nodes;

  assert.equal(apiMapNodeRoleLabel(nodes.find((node) => node.id === 'tool:web_search')!), 'Tool facade');
  assert.equal(apiMapNodeRoleLabel(nodes.find((node) => node.id === 'block:chat.handler')!), 'Implementation');
  assert.match(apiMapNodeRoleDescription({id: 'function:defaultspack:chat_send', kind: 'function', label: 'chat_send', ref: '', metadata: {}}), /operation boundary/);
});
