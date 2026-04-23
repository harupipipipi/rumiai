import assert from 'node:assert/strict';
import test from 'node:test';

import type { ApiStartupCatalog, ApiStartupProfile } from './apiTypes';
import {
  buildStartupProfileView,
  describeStartupActionError,
  describeStartupIssue,
  filterAndSortStartupProfiles,
} from './startupProfiles';

const catalog: ApiStartupCatalog = {
  version: 1,
  start_node: {
    node_id: 'start',
    title: 'start',
    subtitle: 'Official entrypoint',
    kind: 'official_start',
    character: 'S',
    ports: [
      {
        port_id: 'standard',
        label: 'standard',
        direction: 'output',
        contracts: ['rumiai.start.standard.v1'],
        multi: false,
      },
    ],
  },
  slot_specs: [
    {
      slot_id: 'tool',
      label: 'Tool',
      description: 'Tool slot',
      contract: 'rumiai.slot.tool.v1',
      multi: false,
      interface_key: 'rumiai.slot.tool',
      character: 'T',
    },
    {
      slot_id: 'frontend',
      label: 'Frontend',
      description: 'Frontend slot',
      contract: 'rumiai.slot.frontend.v1',
      multi: false,
      interface_key: 'rumiai.slot.frontend',
      character: 'F',
    },
  ],
  standard_packs: [
    {
      pack_id: 'defaultspack',
      display_name: 'Default Pack',
      description: 'Standard pack',
      pack_identity: 'rumi:ecosystem/defaultspack',
      available: true,
      runtime_ready: true,
      runtime_issues: [],
      enabled: true,
      character: 'D',
      slots: [],
    },
  ],
  slot_candidates: {
    tool: [
      {
        pack_id: 'defaultspack',
        pack_identity: 'rumi:ecosystem/defaultspack',
        display_name: 'Default Pack',
        description: 'Standard pack',
        contracts: ['rumiai.slot.tool.v1'],
        component_types: ['tool'],
        provides: ['defaults.tool.invoke'],
        character: 'D',
        enabled: true,
        runtime_ready: true,
        runtime_issues: [],
        selected_component_id: 'tool',
      },
      {
        pack_id: 'broken-tool',
        pack_identity: 'rumi:ecosystem/broken-tool',
        display_name: 'Broken Tool',
        description: 'Broken pack',
        contracts: ['rumiai.slot.tool.v1'],
        component_types: ['tool'],
        provides: ['defaults.tool.invoke'],
        character: 'B',
        enabled: true,
        runtime_ready: false,
        runtime_issues: ["path 'blocks/tool' is missing"],
        selected_component_id: '',
      },
    ],
    frontend: [
      {
        pack_id: 'defaultspack',
        pack_identity: 'rumi:ecosystem/defaultspack',
        display_name: 'Default Pack',
        description: 'Standard pack',
        contracts: ['rumiai.slot.frontend.v1'],
        component_types: ['frontend'],
        provides: ['defaults.frontend.start'],
        character: 'D',
        enabled: true,
        runtime_ready: true,
        runtime_issues: [],
        selected_component_id: 'frontend',
      },
    ],
  },
};

function makeProfile(
  profileId: string,
  name: string,
  updatedAt: number,
  toolPack = 'defaultspack',
): ApiStartupProfile {
  return {
    profile_id: profileId,
    name,
    standard_pack_id: 'defaultspack',
    slots: {
      tool: toolPack,
      frontend: 'defaultspack',
    },
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

test('describeStartupActionError maps auth and slot validation problems to user guidance', () => {
  assert.equal(
    describeStartupActionError('Unauthorized', 'load startup profiles'),
    'Your launcher session expired. Reload the panel and try again.',
  );
  assert.equal(
    describeStartupActionError('API Error: 429 Too Many Requests', 'load startup profiles'),
    'The local panel is receiving too many requests right now. Wait a moment and try again.',
  );
  assert.equal(
    describeStartupActionError("Standard pack 'defaultspack' is not available: Pack 'defaultspack' changed since it was last approved. Re-approve it before launching.", 'save this profile'),
    'The selected standard pack changed after approval. Re-approve it or switch packs before saving.',
  );
  assert.equal(
    describeStartupActionError("Pack 'broken-tool' does not satisfy slot 'tool'", 'save this profile'),
    'Tool only accepts compatible packs. Pick another pack for that slot.',
  );
});

test('buildStartupProfileView marks broken profiles as not ready and surfaces translated issues', () => {
  const readyProfile = makeProfile('ready', 'Ready Profile', 30);
  const brokenProfile = makeProfile('broken', 'Broken Profile', 20, 'broken-tool');

  const readyView = buildStartupProfileView(readyProfile, catalog, 'ready', null);
  assert.equal(readyView.runtimeReady, true);
  assert.equal(readyView.issueCount, 0);
  assert.equal(readyView.badges[0]?.label, 'Active');

  const brokenView = buildStartupProfileView(brokenProfile, catalog, null, 'broken');
  assert.equal(brokenView.runtimeReady, false);
  assert.equal(brokenView.issueCount, 1);
  assert.equal(brokenView.badges.some((badge) => badge.label === 'Last Played'), true);
  assert.match(brokenView.issues[0]?.description ?? '', /Reinstall or repair/);
});

test('filterAndSortStartupProfiles prefers active and ready profiles for recommended view', () => {
  const profiles = [
    buildStartupProfileView(makeProfile('broken', 'Broken Profile', 10, 'broken-tool'), catalog, null, null),
    buildStartupProfileView(makeProfile('active', 'Active Profile', 5), catalog, 'active', null),
    buildStartupProfileView(makeProfile('recent', 'Recent Profile', 30), catalog, null, 'recent'),
  ];

  const recommended = filterAndSortStartupProfiles(profiles, '', 'recommended');
  assert.deepEqual(
    recommended.map((profile) => profile.profile.profile_id),
    ['active', 'recent', 'broken'],
  );

  const filtered = filterAndSortStartupProfiles(profiles, 'broken tool', 'name');
  assert.deepEqual(filtered.map((profile) => profile.profile.profile_id), ['broken']);
});
