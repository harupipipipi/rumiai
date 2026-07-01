import assert from 'node:assert/strict';
import test from 'node:test';
import {renderToStaticMarkup} from 'react-dom/server';

import type {
  ApiStartupCatalog,
  ApiStartupGraphPort,
  ApiStartupNodeDefinition,
  ApiStartupProfile,
} from '@/src/lib/apiTypes';
import {StartupProfilesShell} from './StartupProfiles';

function surfacePort(): ApiStartupGraphPort {
  return {
    port_key: 'frontend.surface',
    node_id: 'frontend',
    port_id: 'surface',
    target_node_ref: 'defaultspack.frontend',
    target_port: {id: 'surface', direction: 'input', standards: ['rumi.surface']},
    source_node_id: 'frontend',
    source_node_ref: 'defaultspack.frontend',
    source_port_id: 'surface',
    source_port: {id: 'surface', direction: 'output', standards: ['rumi.surface']},
    source_ref: 'frontend.surface',
  };
}

function startupNode(
  nodeId: string,
  componentType: 'frontend' | 'tool',
  standards: string[],
  label: string,
): ApiStartupNodeDefinition {
  return {
    node_id: nodeId,
    kind: componentType === 'frontend' ? 'ecosystem.surface' : 'tool.bundle',
    component_id: componentType,
    component_type: componentType,
    display_name: {en: label},
    ports: [{id: componentType === 'frontend' ? 'surface' : 'tools', direction: 'output', standards}],
    metadata: componentType === 'frontend'
      ? {launch: {kind: 'desktop_app', pack_id: nodeId.split('.')[0], surface: 'browser'}}
      : {},
  };
}

function sampleCatalog(): ApiStartupCatalog {
  return {
    version: 3,
    packs: [
      {
        pack_id: 'defaultspack',
        name: 'Defaults Pack',
        description: 'Base local runtime',
        pack_identity: 'rumi:ecosystem/defaultspack',
        available: true,
        enabled: true,
        approval_issues: [],
        graphs: [{graph_id: 'defaultspack.startup', display_name: {en: 'Default Startup'}}],
        nodes: [
          startupNode('defaultspack.frontend', 'frontend', ['rumi.surface'], 'Default Frontend'),
          startupNode('defaultspack.tool', 'tool', ['rumi.tool.bundle'], 'Default Tools'),
        ],
      },
      {
        pack_id: 'frontendpack',
        name: 'Browser Frontend Pack',
        description: 'Replacement frontend',
        pack_identity: 'rumi:ecosystem/frontendpack',
        available: true,
        enabled: true,
        approval_issues: [],
        graphs: [],
        nodes: [startupNode('frontendpack.web_surface', 'frontend', ['rumi.surface'], 'Browser Surface')],
      },
      {
        pack_id: 'searchpack',
        name: 'Search Tool Pack',
        description: 'Search tool bundle',
        pack_identity: 'rumi:ecosystem/searchpack',
        available: true,
        enabled: true,
        approval_issues: [],
        graphs: [],
        nodes: [startupNode('searchpack.tool', 'tool', ['rumi.tool.bundle'], 'Search Tools')],
      },
    ],
  };
}

function sampleProfile(): ApiStartupProfile {
  return {
    version: 3,
    profile_id: 'mock-profile',
    name: 'Mock Profile',
    base_pack: 'defaultspack',
    graph_id: 'defaultspack.startup',
    graph_ports: [surfacePort()],
    packs: ['defaultspack'],
    node_overrides: {},
    created_at: 1,
    updated_at: 1,
    default_graph: 'defaultspack.startup',
    capability_profile_id: 'defaultspack.startup',
    launch_capability_graph: true,
    policy: {enforce_api_route_allowlist: true},
  };
}

test('StartupProfilesShell separates profile pack selection and security controls', () => {
  const markup = renderToStaticMarkup(
    <StartupProfilesShell
      activeProfileId="mock-profile"
      catalog={sampleCatalog()}
      lastLaunchedProfileId={null}
      preview={null}
      profiles={[sampleProfile()]}
      selectedProfileId="mock-profile"
      onActivate={() => {}}
      onAddPack={() => {}}
      onCreateProfile={() => {}}
      onDeleteProfile={() => {}}
      onDuplicateProfile={() => {}}
      onLaunch={() => {}}
      onPreview={() => {}}
      onRemovePack={() => {}}
      onSelectBasePack={() => {}}
      onSelectFrontend={() => {}}
      onSelectProfile={() => {}}
      onToggleLaunchCompile={() => {}}
      onTogglePolicy={() => {}}
    />,
  );

  assert.match(markup, /Startup Profiles/);
  assert.match(markup, /Profile-local packs are separate from the global pack enablement page/);
  assert.match(markup, /Launch Frontend/);
  assert.match(markup, /aria-label="Launch frontend"/);
  assert.match(markup, /aria-label="Base pack"/);
  assert.match(markup, /Browser Frontend Pack \/ Browser Surface/);
  assert.match(markup, /Tool Packs/);
  assert.match(markup, /Search Tool Pack/);
  assert.match(markup, /Add Pack/);
  assert.match(markup, /Profile Security/);
  assert.match(markup, /Compile capability graph before launch/);
  assert.match(markup, /aria-label="Compile capability graph before launch"/);
  assert.match(markup, /aria-label="Require clean graph compile"/);
  assert.match(markup, /aria-label="Enforce API route allowlist"/);
});
