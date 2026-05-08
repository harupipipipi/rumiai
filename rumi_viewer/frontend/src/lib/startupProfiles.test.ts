import assert from 'node:assert/strict';
import test from 'node:test';

import type { ApiStartupCatalog, ApiStartupProfile } from './apiTypes';
import {
  buildStartupProfileView,
  compatibleNodesForPort,
  defaultBasePack,
  describeStartupActionError,
  describeStartupIssue,
  filterAndSortStartupProfiles,
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
