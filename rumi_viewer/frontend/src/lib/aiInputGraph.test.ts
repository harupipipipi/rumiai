import assert from 'node:assert/strict';
import test from 'node:test';

import {
  aiInputEffectiveToolIds,
  aiInputHeavyNodes,
  insertConditionGate,
  normalizeAiInputConfig,
  toggleAiInputEdge,
} from '@/src/lib/aiInputGraph';
import type {ApiAiInputEdge, StartupProfileAiInputResponseData} from '@/src/lib/apiTypes';

test('toggleAiInputEdge adds and removes disabled edges', () => {
  const config = normalizeAiInputConfig({disabled_edges: ['edge:b']});
  const disabled = toggleAiInputEdge(config, 'edge:a', true);
  const enabled = toggleAiInputEdge(disabled, 'edge:a', false);

  assert.deepEqual(disabled.disabled_edges, ['edge:a', 'edge:b']);
  assert.deepEqual(enabled.disabled_edges, ['edge:b']);
});

test('aiInputHeavyNodes sorts by token cost', () => {
  const data = {
    token_estimate: {
      total: 9,
      by_port: {},
      by_node: {
        small: 1,
        large: 8,
      },
    },
    effective_input: {tool_schemas: []},
  } as unknown as StartupProfileAiInputResponseData;

  assert.deepEqual(aiInputHeavyNodes(data), [{id: 'large', tokens: 8}, {id: 'small', tokens: 1}]);
});

test('aiInputEffectiveToolIds returns enabled tool ids', () => {
  const data = {
    effective_input: {
      tool_schemas: [
        {tool_id: 'web_search', name: 'web_search'},
        {tool_id: 'computer_use', name: 'computer_use'},
      ],
    },
    token_estimate: {by_node: {}},
  } as unknown as StartupProfileAiInputResponseData;

  assert.deepEqual(aiInputEffectiveToolIds(data), ['web_search', 'computer_use']);
});

test('insertConditionGate disables original edge and inserts gate wiring', () => {
  const edge: ApiAiInputEdge = {
    id: 'edge:prompt:browser->model_input:default.system',
    from_id: 'prompt:browser',
    from_port: 'output',
    to_id: 'model_input:default',
    to_port: 'system',
    kind: 'contributes_to',
    active: true,
    gate_id: null,
    metadata: {},
  };
  const config = insertConditionGate(normalizeAiInputConfig(null), edge, {
    field: 'message',
    op: 'contains',
    value: 'ブラウザ',
  });

  assert.deepEqual(config.disabled_edges, [edge.id]);
  assert.equal(Object.keys(config.gates).length, 1);
  assert.equal(config.inserted_edges.length, 2);
  assert.equal(config.inserted_edges[0]?.metadata.replaces_edge, edge.id);
});
