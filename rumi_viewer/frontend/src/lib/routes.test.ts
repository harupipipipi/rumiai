import test from 'node:test';
import assert from 'node:assert/strict';

import { apiMapRoute, panelRoutes, profileGraphRoute } from './routes';

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

test('profile routes can carry focused profile context', () => {
  assert.equal(profileGraphRoute('default-profile'), '/profile-graph?profile=default-profile');
  assert.equal(apiMapRoute({ profileId: 'default-profile', focus: 'profile:default-profile' }), '/api-map?profile_id=default-profile&focus=profile%3Adefault-profile');
  assert.equal(apiMapRoute({ profileId: 'default-profile' }), '/api-map?profile_id=default-profile');
});
