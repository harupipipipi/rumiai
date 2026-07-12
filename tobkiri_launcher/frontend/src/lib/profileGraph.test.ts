import assert from 'node:assert/strict';
import test from 'node:test';

import {
  addProfileGraphSelection,
  normalizeProfileGraphDocument,
  removeProfileGraphSelection,
} from './profileGraph';

test('addProfileGraphSelection adds profile-to-tool edge and selected.tools entry', () => {
  const document = normalizeProfileGraphDocument('research-profile', {
    version: 1,
    profile_id: 'research-profile',
    nodes: [],
    edges: [],
    selected: {tools: [], webhooks: [], api_routes: [], prompts: [], frontend: [], flows: [], nodes: []},
  });

  const next = addProfileGraphSelection(document, 'tools', {
    id: 'web_search',
    label: 'Web Search',
    kind: 'tool',
  });

  assert.deepEqual(next.selected.tools, ['web_search']);
  assert.equal(next.nodes.some((node) => node.id === 'tool:web_search'), true);
  assert.equal(
    next.edges.some((edge) => edge.from_id === 'profile:research-profile' && edge.to_id === 'tool:web_search' && edge.kind === 'selects'),
    true,
  );
});

test('addProfileGraphSelection adds prompts without duplicating entries', () => {
  const document = normalizeProfileGraphDocument('research-profile', {
    version: 1,
    profile_id: 'research-profile',
    nodes: [],
    edges: [],
    selected: {tools: [], webhooks: [], api_routes: [], prompts: ['research.system'], frontend: [], flows: [], nodes: []},
  });

  const next = addProfileGraphSelection(document, 'prompts', {
    id: 'research.system',
    label: 'Research Prompt',
    kind: 'prompt',
  });

  assert.deepEqual(next.selected.prompts, ['research.system']);
  assert.equal(next.nodes.some((node) => node.id === 'prompt:research.system'), true);
});

test('removeProfileGraphSelection prunes the selected entry and its direct edge', () => {
  const document = addProfileGraphSelection(
    normalizeProfileGraphDocument('research-profile', {
      version: 1,
      profile_id: 'research-profile',
      nodes: [],
      edges: [],
      selected: {tools: [], webhooks: [], api_routes: [], prompts: [], frontend: [], flows: [], nodes: []},
    }),
    'frontend',
    {id: 'research_sidebar', label: 'Research Sidebar', kind: 'frontend'},
  );

  const next = removeProfileGraphSelection(document, 'frontend', 'research_sidebar');

  assert.deepEqual(next.selected.frontend, []);
  assert.equal(next.edges.some((edge) => edge.to_id === 'frontend:research_sidebar'), false);
});
