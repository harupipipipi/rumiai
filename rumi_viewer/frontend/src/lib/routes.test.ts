import test from 'node:test';
import assert from 'node:assert/strict';

import { panelRoutes } from './routes';

test('panel routes stay basename-relative', () => {
  assert.equal(panelRoutes.home, '/');
  assert.equal(panelRoutes.setup, '/setup');
  assert.equal(panelRoutes.packs, '/packs');
  assert.equal(panelRoutes.nodes, '/nodes');
  assert.equal(panelRoutes.graphEditor, '/graphs');
  assert.equal(panelRoutes.profileGraph, '/profile-graph');
  assert.equal(panelRoutes.apiMap, '/api-map');
  assert.equal(panelRoutes.profileWorkspace, '/profile-workspace');
  assert.equal(panelRoutes.flows, '/flows');
  assert.equal(panelRoutes.settings, '/settings');
  assert.equal(panelRoutes.packDetail('defaultspack'), '/packs/defaultspack');
});
