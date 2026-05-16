import test from 'node:test';
import assert from 'node:assert/strict';

import {
  PANEL_BASENAME,
  panelChildRoutes,
  panelPackDetailRoute,
  panelRoutes,
  toPanelChildRoutePath,
} from './routes';

test('panel routes stay basename-relative', () => {
  assert.equal(PANEL_BASENAME, '/panel');
  assert.equal(panelRoutes.home, '/');
  assert.equal(panelRoutes.setup, '/setup');
  assert.equal(panelRoutes.packs, '/packs');
  assert.equal(panelRoutes.nodes, '/nodes');
  assert.equal(panelRoutes.graphEditor, '/graphs');
  assert.equal(panelRoutes.startup, '/startup');
  assert.equal(panelRoutes.flows, '/flows');
  assert.equal(panelRoutes.settings, '/settings');
  assert.equal(panelRoutes.packDetail('defaultspack'), '/packs/defaultspack');
});

test('nested app route config uses react-router child paths', () => {
  assert.deepEqual(
    panelChildRoutes.map(route => ({ key: route.key, path: route.path, index: Boolean(route.index) })),
    [
      { key: 'dashboard', path: '', index: true },
      { key: 'packs', path: 'packs', index: false },
      { key: 'nodes', path: 'nodes', index: false },
      { key: 'graphEditor', path: 'graphs', index: false },
      { key: 'startup', path: 'startup', index: false },
      { key: 'flows', path: 'flows', index: false },
      { key: 'settings', path: 'settings', index: false },
    ],
  );
  assert.equal(toPanelChildRoutePath(panelRoutes.setup), 'setup');
  assert.equal(panelPackDetailRoute.path, 'packs/:id');
});
