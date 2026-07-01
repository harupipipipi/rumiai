import assert from 'node:assert/strict';
import test from 'node:test';

import type { ApiStartupCatalog, ApiStartupProfile } from './apiTypes';
import {
  buildAddStartupProfilePackPatch,
  buildRemoveStartupProfilePackPatch,
  buildSetStartupProfileBasePackPatch,
  buildStartupProfileView,
  compatibleNodesForPort,
  defaultBasePack,
  describeStartupActionError,
  describeStartupIssue,
  filterAndSortStartupProfiles,
  startupPacksByRole,
  startupPacksForRole,
} from './startupProfiles';

const catalog: ApiStartupCatalog = {
  version: 2,
  packs: [
    {
      pack_id: 'defaultspack',
      name: 'Default Pack',
      description: 'Base pack',
      pack_identity: 'rumi:ecosystem/defaultspack',
      available: true,
      enabled: true,
      approval_issues: [],
      graphs: [{ graph_id: 'defaultspack.startup', display_name: { en: 'Startup' } }],
      nodes: [
        {
          node_id: 'rumi.start',
          kind: 'core.builtin',
          component_id: 'start',
          component_type: 'flow_start',
          ports: [{ id: 'out', direction: 'output', standards: ['rumi.flow.start'] }],
        },
        {
          node_id: 'defaultspack.ai_client',
          kind: 'component',
          component_id: 'ai_client',
          component_type: 'ai_client',
          ports: [{ id: 'client', direction: 'output', standards: ['rumi.ai.client'] }],
        },
        {
          node_id: 'defaultspack.tool',
          kind: 'component',
          component_id: 'tool',
          component_type: 'tool',
          ports: [{ id: 'tools', direction: 'output', standards: ['rumi.tool.bundle'] }],
        },
      ],
    },
    {
      pack_id: 'graphpack',
      name: 'Graph Pack',
      description: 'Alternative startup graph',
      pack_identity: 'rumi:ecosystem/graphpack',
      available: true,
      enabled: true,
      approval_issues: [],
      graphs: [{ graph_id: 'graphpack.startup', display_name: { en: 'Graph Startup' } }],
      nodes: [],
    },
    {
      pack_id: 'coolpack',
      name: 'Cool Pack',
      description: 'Alternative AI',
      pack_identity: 'rumi:ecosystem/coolpack',
      available: true,
      enabled: true,
      approval_issues: [],
      graphs: [],
      nodes: [
        {
          node_id: 'rumi.start',
          kind: 'core.builtin',
          component_id: 'start',
          component_type: 'flow_start',
          ports: [{ id: 'out', direction: 'output', standards: ['rumi.flow.start'] }],
        },
        {
          node_id: 'coolpack.ai_client',
          kind: 'component',
          component_id: 'ai_client',
          component_type: 'ai_client',
          ports: [{ id: 'client', direction: 'output', standards: ['rumi.ai.client'] }],
        },
      ],
    },
    {
      pack_id: 'bundlepack',
      name: 'Bundle Pack',
      description: 'Tool bundle without a tool component type',
      pack_identity: 'rumi:ecosystem/bundlepack',
      available: true,
      enabled: true,
      approval_issues: [],
      graphs: [],
      nodes: [
        {
          node_id: 'bundlepack.actions',
          kind: 'component',
          component_id: 'actions',
          component_type: 'capability',
          ports: [{ id: 'tools', direction: 'output', standards: ['rumi.tool.bundle'] }],
        },
      ],
    },
    {
      pack_id: 'blockedpack',
      name: 'Blocked Pack',
      description: 'Needs approval',
      pack_identity: 'rumi:ecosystem/blockedpack',
      available: false,
      enabled: true,
      approval_issues: ["Pack 'blockedpack' changed since it was last approved. Re-approve it before launching."],
      graphs: [],
      nodes: [],
    },
    {
      pack_id: 'frontendpack',
      name: 'Frontend Pack',
      description: 'Alternative frontend',
      pack_identity: 'rumi:ecosystem/frontendpack',
      available: true,
      enabled: true,
      approval_issues: [],
      graphs: [],
      nodes: [
        {
          node_id: 'frontendpack.web_surface',
          kind: 'ecosystem.surface',
          component_id: 'web',
          component_type: 'frontend',
          metadata: {
            pack_id: 'frontendpack',
            component_type: 'frontend',
            component_id: 'web',
            source_path: 'ecosystem/frontendpack/components/web/node.json',
          },
          ports: [{ id: 'surface', direction: 'output', standards: ['rumi.surface'] }],
        },
      ],
    },
    {
      pack_id: 'surfacepack',
      name: 'Surface Pack',
      description: 'Alternative surface',
      pack_identity: 'rumi:ecosystem/surfacepack',
      available: true,
      enabled: true,
      approval_issues: [],
      graphs: [],
      nodes: [
        {
          node_id: 'surfacepack.surface',
          kind: 'ecosystem.surface',
          component_id: 'surface',
          component_type: 'component',
          ports: [{ id: 'surface', direction: 'output', standards: ['rumi.surface'] }],
        },
      ],
    },
  ],
};

function makeProfile(
  profileId: string,
  name: string,
  updatedAt: number,
  overrides: Record<string, string> = {},
  packs = ['defaultspack', 'coolpack'],
): ApiStartupProfile {
  return {
    version: 3,
    profile_id: profileId,
    name,
    base_pack: 'defaultspack',
    graph_id: 'defaultspack.startup',
    packs,
    node_overrides: overrides,
    graph_ports: [
      {
        port_key: 'agent.ai',
        node_id: 'agent',
        port_id: 'ai',
        target_node_ref: 'defaultspack.agent',
        target_port: { id: 'ai', direction: 'input', standards: ['rumi.ai.client'] },
        source_node_id: 'ai',
        source_node_ref: 'defaultspack.ai_client',
        source_port_id: 'client',
        source_port: { id: 'client', direction: 'output', standards: ['rumi.ai.client'] },
        source_ref: 'ai.client',
      },
    ],
    created_at: updatedAt,
    updated_at: updatedAt,
  };
}

function makeFrontendProfile(
  profileId: string,
  packs = ['defaultspack'],
  overrides: Record<string, string> = {},
): ApiStartupProfile {
  const profile = makeProfile(profileId, 'Frontend Profile', 50, overrides, packs);
  profile.graph_ports = [
    {
      port_key: 'frontend.surface',
      node_id: 'frontend',
      port_id: 'surface',
      target_node_ref: 'defaultspack.frontend',
      target_port: { id: 'surface', direction: 'input', standards: ['rumi.surface'] },
      source_node_id: 'cli',
      source_node_ref: 'defaultspack.cli_surface',
      source_port_id: 'surface',
      source_port: { id: 'surface', direction: 'output', standards: ['rumi.surface'] },
      source_ref: 'cli.surface',
    },
  ];
  return profile;
}

test('describeStartupIssue translates approval and filesystem failures', () => {
  assert.deepEqual(
    describeStartupIssue("Pack 'defaultspack' changed since it was last approved. Re-approve it before launching.", 'Tool'),
    {
      title: 'Tool needs attention',
      description: 'This pack changed after approval. Re-approve it before launch.',
      severity: 'warning',
    },
  );

  assert.deepEqual(
    describeStartupIssue("path 'blocks/tool' is missing", 'Tool'),
    {
      title: 'Tool is incomplete',
      description: 'Required files are missing at blocks/tool. Reinstall or repair the pack.',
      severity: 'danger',
    },
  );
});

test('describeStartupActionError maps v3 validation problems to user guidance', () => {
  assert.equal(
    describeStartupActionError('Unauthorized', 'load startup profiles'),
    'Your launcher session expired. Reload the panel and try again.',
  );
  assert.equal(
    describeStartupActionError('base_pack is required', 'create a profile'),
    'Choose a base pack before creating this profile.',
  );
  assert.equal(
    describeStartupActionError("Node 'coolpack.tool' does not satisfy port 'agent.ai'. Required standards: ['rumi.ai.client']. Provided standards: ['rumi.tool.bundle']", 'save this profile'),
    'That node does not provide the standard required by this graph port.',
  );
});

test('buildStartupProfileView renders v3 catalog packs, ports, and overrides', () => {
  const readyProfile = makeProfile('ready', 'Ready Profile', 30, { 'agent.ai': 'coolpack.ai_client' });
  const readyView = buildStartupProfileView(readyProfile, catalog, 'ready', null);
  assert.equal(readyView.runtimeReady, true);
  assert.equal(readyView.issueCount, 0);
  assert.equal(readyView.badges[0]?.label, 'Active');
  assert.equal(readyView.basePack?.pack_id, 'defaultspack');
  assert.equal(readyView.ports[0]?.resolvedNode, 'coolpack.ai_client');

  const brokenProfile = makeProfile('broken', 'Broken Profile', 20, { 'agent.ai': 'defaultspack.tool' });
  const brokenView = buildStartupProfileView(brokenProfile, catalog, null, 'broken');
  assert.equal(brokenView.runtimeReady, false);
  assert.equal(brokenView.issueCount, 1);
  assert.equal(brokenView.badges.some((badge) => badge.label === 'Last Played'), true);
  assert.match(brokenView.issues[0]?.description ?? '', /rumi\.ai\.client/);
});

test('compatibleNodesForPort returns only output nodes matching target standards', () => {
  const profile = makeProfile('ready', 'Ready Profile', 30);
  const compatible = compatibleNodesForPort(catalog, profile, profile.graph_ports[0]);
  assert.deepEqual(compatible.map((node) => node.node_id), ['coolpack.ai_client', 'defaultspack.ai_client']);
});

test('compatibleNodesForPort includes component surface nodes from selected packs', () => {
  const profile = makeProfile('frontend', 'Frontend Profile', 45, {}, ['defaultspack', 'frontendpack']);
  profile.graph_ports = [
    {
      port_key: 'frontend.surface',
      node_id: 'frontend',
      port_id: 'surface',
      target_node_ref: 'defaultspack.frontend',
      target_port: { id: 'surface', direction: 'input', standards: ['rumi.surface'] },
      source_node_id: 'cli',
      source_node_ref: 'defaultspack.cli_surface',
      source_port_id: 'surface',
      source_port: { id: 'surface', direction: 'output', standards: ['rumi.surface'] },
      source_ref: 'cli.surface',
    },
  ];

  const compatible = compatibleNodesForPort(catalog, profile, profile.graph_ports[0]);

  assert.deepEqual(compatible.map((node) => node.node_id), ['frontendpack.web_surface']);
});

test('buildStartupProfileView treats the core start node default as healthy', () => {
  const profile = makeProfile('start-ready', 'Start Ready Profile', 40);
  profile.graph_ports = [
    {
      port_key: 'agent.start',
      node_id: 'agent',
      port_id: 'start',
      target_node_ref: 'defaultspack.agent',
      target_port: { id: 'start', direction: 'input', standards: ['rumi.flow.start'] },
      source_node_id: 'start',
      source_node_ref: 'rumi.start',
      source_port_id: 'out',
      source_port: { id: 'out', direction: 'output', standards: ['rumi.flow.start'] },
      source_ref: 'start.out',
    },
  ];

  const view = buildStartupProfileView(profile, catalog, 'start-ready', null);

  assert.equal(view.runtimeReady, true);
  assert.equal(view.issueCount, 0);
  assert.deepEqual(compatibleNodesForPort(catalog, profile, profile.graph_ports[0]).map((node) => node.node_id), ['rumi.start']);
});

test('filterAndSortStartupProfiles prefers active and ready profiles for recommended view', () => {
  const profiles = [
    buildStartupProfileView(makeProfile('broken', 'Broken Profile', 10, { 'agent.ai': 'defaultspack.tool' }), catalog, null, null),
    buildStartupProfileView(makeProfile('active', 'Active Profile', 5), catalog, 'active', null),
    buildStartupProfileView(makeProfile('recent', 'Recent Profile', 30), catalog, null, 'recent'),
  ];

  const recommended = filterAndSortStartupProfiles(profiles, '', 'recommended');
  assert.deepEqual(
    recommended.map((profile) => profile.profile.profile_id),
    ['active', 'recent', 'broken'],
  );

  const filtered = filterAndSortStartupProfiles(profiles, 'cool pack', 'name');
  assert.deepEqual(filtered.map((profile) => profile.profile.profile_id), ['active', 'broken', 'recent']);
});

test('defaultBasePack picks the first available pack with graphs', () => {
  assert.equal(defaultBasePack(catalog)?.pack_id, 'defaultspack');
});

test('startupPacksByRole groups available base, frontend, and tool packs', () => {
  const options = startupPacksByRole(catalog);

  assert.deepEqual(options.basePacks.map((pack) => pack.pack_id), ['defaultspack', 'graphpack']);
  assert.deepEqual(options.frontendPacks.map((pack) => pack.pack_id), ['frontendpack', 'surfacepack']);
  assert.deepEqual(options.toolPacks.map((pack) => pack.pack_id), ['defaultspack', 'bundlepack']);
  assert.deepEqual(startupPacksForRole(catalog, 'frontend').map((pack) => pack.pack_id), ['frontendpack', 'surfacepack']);
});

test('buildAddStartupProfilePackPatch adds pack IDs once and selects compatible frontend override', () => {
  const profile = makeFrontendProfile('frontend-add');
  const patch = buildAddStartupProfilePackPatch(catalog, profile, 'frontendpack');

  assert.deepEqual(patch.packs, ['defaultspack', 'frontendpack']);
  assert.deepEqual(patch.node_overrides, { 'frontend.surface': 'frontendpack.web_surface' });

  const duplicatePatch = buildAddStartupProfilePackPatch(
    catalog,
    { ...profile, packs: patch.packs ?? profile.packs, node_overrides: patch.node_overrides ?? {} },
    'frontendpack',
  );
  assert.deepEqual(duplicatePatch.packs, ['defaultspack', 'frontendpack']);
});

test('buildRemoveStartupProfilePackPatch removes stale overrides and repairs frontend overrides', () => {
  const profile = makeFrontendProfile(
    'frontend-remove',
    ['defaultspack', 'frontendpack', 'surfacepack', 'coolpack'],
    {
      'frontend.surface': 'frontendpack.web_surface',
      'agent.ai': 'coolpack.ai_client',
    },
  );
  profile.graph_ports.push(makeProfile('ai-port', 'AI Profile', 60).graph_ports[0]);

  const withoutCoolPack = buildRemoveStartupProfilePackPatch(catalog, profile, 'coolpack');
  assert.deepEqual(withoutCoolPack.packs, ['defaultspack', 'frontendpack', 'surfacepack']);
  assert.deepEqual(withoutCoolPack.node_overrides, { 'frontend.surface': 'frontendpack.web_surface' });

  const withoutFrontendPack = buildRemoveStartupProfilePackPatch(catalog, {
    ...profile,
    packs: withoutCoolPack.packs ?? profile.packs,
    node_overrides: withoutCoolPack.node_overrides ?? {},
  }, 'frontendpack');
  assert.deepEqual(withoutFrontendPack.packs, ['defaultspack', 'surfacepack']);
  assert.deepEqual(withoutFrontendPack.node_overrides, { 'frontend.surface': 'surfacepack.surface' });
});

test('buildSetStartupProfileBasePackPatch switches graph and keeps base pack selected', () => {
  const profile = makeProfile('base-switch', 'Base Switch', 70, {}, ['defaultspack', 'coolpack']);
  const patch = buildSetStartupProfileBasePackPatch(catalog, profile, 'graphpack');

  assert.equal(patch.base_pack, 'graphpack');
  assert.equal(patch.graph_id, 'graphpack.startup');
  assert.deepEqual(patch.packs, ['graphpack', 'defaultspack', 'coolpack']);
});
