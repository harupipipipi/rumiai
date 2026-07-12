import assert from 'node:assert/strict';
import {test} from 'node:test';

import {
  capabilityNodeLabel,
  capabilityPortLabel,
  normalizeCapabilityProfileNodes,
} from './nodeCatalog.ts';

test('normalizes legacy profile node payloads without palette_nodes', () => {
  const node = {
    node_id: 'defaultspack.agent',
    label: null,
    description_label: null,
    kind: 'ecosystem.agent',
    display_name: {ja: 'エージェント', en: 'Agent'},
    description: {},
    ports: [
      {
        id: 'start',
        direction: 'input' as const,
        display_name: {ja: '開始', en: 'Start'},
        standards: ['rumi.flow.start'],
      },
    ],
    bindings: {},
    metadata: {},
  };

  const normalized = normalizeCapabilityProfileNodes({
    profile_id: 'defaultspack.startup',
    nodes: [node],
    count: 1,
  });

  assert.equal(normalized.nodes.length, 1);
  assert.equal(normalized.paletteNodes.length, 1);
  assert.equal(capabilityNodeLabel(normalized.nodes[0]), 'Agent');
  assert.equal(capabilityPortLabel(normalized.nodes[0].ports[0]), 'Start');
});

test('normalizes current profile node payloads with explicit palette_nodes', () => {
  const disabledNode = {
    node_id: 'sample.tool',
    label: 'Tool',
    description_label: '',
    kind: 'ecosystem.tool',
    ports: [],
    bindings: {},
    metadata: {},
    state: {
      node_id: 'sample.tool',
      installed: true,
      approved: true,
      enabled: false,
      configured: true,
      status: 'disabled',
      missing: [],
    },
  };

  const normalized = normalizeCapabilityProfileNodes({
    profile: {
      profile_id: 'coding',
      label: 'Coding',
      description_label: '',
      permissions: {},
      enabled_nodes: [],
      disabled_nodes: [],
      node_settings: {},
      policy: {},
    },
    nodes: [disabledNode],
    node_state: [disabledNode.state],
    palette_nodes: [],
    count: 1,
    palette_count: 0,
  });

  assert.equal(normalized.profile?.profile_id, 'coding');
  assert.equal(normalized.nodes.length, 1);
  assert.equal(normalized.paletteNodes.length, 0);
});
