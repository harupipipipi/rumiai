import assert from 'node:assert/strict';
import test from 'node:test';
import {renderToStaticMarkup} from 'react-dom/server';

import type {ApiStartupProfile, StartupProfileGraphResponseData} from '@/src/lib/apiTypes';
import {normalizeProfileGraphDocument} from '@/src/lib/profileGraph';
import {
  createProfileGraphEditorActions,
  ProfileGraphEditorShell,
} from './ProfileGraphEditor';

function sampleProfile(): ApiStartupProfile {
  return {
    version: 3,
    profile_id: 'research-profile',
    name: 'Research Profile',
    base_pack: 'defaultspack',
    graph_id: 'defaultspack.startup',
    graph_ports: [],
    packs: ['defaultspack'],
    node_overrides: {},
    created_at: 1,
    updated_at: 1,
  };
}

function sampleGraphResponse(): StartupProfileGraphResponseData {
  return {
    profile_id: 'research-profile',
    profile: sampleProfile(),
    graph: {
      version: 1,
      profile_id: 'research-profile',
      nodes: [
        {id: 'profile:research-profile', kind: 'profile', label: 'Research Profile', ref: 'research-profile', metadata: {}},
      ],
      edges: [],
      selected: {tools: [], webhooks: [], api_routes: [], prompts: [], frontend: [], flows: [], nodes: []},
    },
    available: {
      tools: [{id: 'web_search', label: 'Web Search', kind: 'tool'}],
      webhooks: [{id: 'research-webhook', label: 'Research Webhook', kind: 'webhook'}],
      api_routes: [{id: 'POST /api/chat/conversations/{id}/messages', label: 'POST /api/chat/conversations/{id}/messages', kind: 'api'}],
      prompts: [{id: 'research.system', label: 'Research Rule', kind: 'prompt'}],
      frontend: [{id: 'research_sidebar', label: 'Research Sidebar', kind: 'frontend'}],
      flows: [{id: 'research.flow', label: 'Research Flow', kind: 'flow'}],
      capability_nodes: [{id: 'research.node', label: 'Research Node', kind: 'node'}],
    },
    summary: {
      selected_tool_count: 0,
      available_tool_count: 1,
      selected_webhook_count: 0,
      available_webhook_count: 1,
      api_route_count: 1,
      selected_frontend_count: 0,
      selected_prompt_count: 0,
    },
    diagnostics: [],
  };
}

test('ProfileGraphEditorShell renders category buttons for runtime wiring', () => {
  const graphData = sampleGraphResponse();
  const markup = renderToStaticMarkup(
    <ProfileGraphEditorShell
      profiles={[sampleProfile()]}
      activeProfileId="research-profile"
      selectedProfileId="research-profile"
      graphData={graphData}
      draft={normalizeProfileGraphDocument('research-profile', graphData.graph)}
      preview={null}
      activeCategory="tools"
      paletteSearch=""
      selectedNodeId="profile:research-profile"
      onSelectProfile={() => {}}
      onCategoryChange={() => {}}
      onPaletteSearchChange={() => {}}
      onAddCandidate={() => {}}
      onSelectNode={() => {}}
      onRemoveSelection={() => {}}
      onApply={() => {}}
      onPreview={() => {}}
      onLaunch={() => {}}
    />,
  );

  assert.match(markup, /\+ Tool/);
  assert.match(markup, /\+ Webhook/);
  assert.match(markup, /\+ API/);
  assert.match(markup, /\+ Rule/);
  assert.match(markup, /\+ Frontend/);
});

test('createProfileGraphEditorActions forwards apply and preview to the graph API helpers', async () => {
  const calls: Array<{kind: string; profileId: string; payload?: unknown}> = [];
  const actions = createProfileGraphEditorActions({
    update: async (profileId, payload) => {
      calls.push({kind: 'apply', profileId, payload});
      return sampleGraphResponse();
    },
    preview: async (profileId, payload) => {
      calls.push({kind: 'preview', profileId, payload});
      return {
        ...sampleGraphResponse(),
        compile_preview: {
          ok: true,
          profile_id: 'research-profile',
          profile: sampleProfile(),
          capability_graph: {ok: true, diagnostics: []},
          diagnostics: [],
        },
        profile_graph_runtime_preview: {
          selected: {tools: [], webhooks: [], api_routes: [], prompts: [], frontend: [], flows: [], nodes: []},
          policy: {},
          tool_filter_result: [],
          prompt_resolution: {},
          webhook_status: [],
          api_route_policy: {},
          frontend_selection: [],
          diagnostics: [],
        },
      };
    },
    launch: async (profileId) => {
      calls.push({kind: 'launch', profileId});
      return {profile: sampleProfile()};
    },
  });

  const document = normalizeProfileGraphDocument('research-profile', sampleGraphResponse().graph);
  await actions.apply('research-profile', document);
  await actions.preview('research-profile', document);

  assert.equal(calls[0]?.kind, 'apply');
  assert.equal(calls[0]?.profileId, 'research-profile');
  assert.deepEqual(calls[0]?.payload, {
    graph: {
      version: 1,
      nodes: document.nodes,
      edges: document.edges,
    },
    selected: document.selected,
  });
  assert.equal(calls[1]?.kind, 'preview');
  assert.equal(calls[1]?.profileId, 'research-profile');
});
