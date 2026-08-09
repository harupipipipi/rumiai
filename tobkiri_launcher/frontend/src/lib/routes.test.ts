import test from 'node:test';
import assert from 'node:assert/strict';

import {
  panelRouteMeta,
  panelRoutes,
  panelRouteTitleKey,
  viewerNavGroups,
} from './routes';

test('panel routes stay basename-relative', () => {
  assert.equal(panelRoutes.home, '/');
  assert.equal(panelRoutes.setup, '/setup');
  assert.equal(panelRoutes.packs, '/packs');
  assert.equal(panelRoutes.packDetail('defaultspack'), '/packs/defaultspack');
});

test('registered panel routes expose stable header title metadata', () => {
  const registeredRoutes = ['home', 'setup', 'packs'] as const;

  for (const route of registeredRoutes) {
    assert.equal(panelRouteTitleKey(panelRouteMeta[route].path), panelRouteMeta[route].titleKey);
    assert.match(panelRouteMeta[route].titleKey, /^nav\./);
  }

  assert.equal(panelRouteTitleKey('/packs/defaultspack'), panelRouteMeta.packs.titleKey);
  assert.equal(panelRouteTitleKey('/unknown-route'), 'nav.unknown');
});

test('viewer navigation groups use route metadata and i18n keys', () => {
  const navRoutes = new Set<string>(viewerNavGroups.flatMap((group) => group.routes));
  assert.ok(navRoutes.has('packs'));
  assert.ok(!navRoutes.has('settings'));
  assert.ok(!navRoutes.has('startup'));

  for (const group of viewerNavGroups) {
    assert.match(group.labelKey, /^nav\./);
    for (const route of group.routes) {
      assert.match(panelRouteMeta[route].navKey || '', /^nav\./);
    }
  }
});

test('retired advanced panel paths are not registered', () => {
  for (const path of [
    '/nodes',
    '/graphs',
    '/profile-graph',
    '/ai-input',
    '/api-map',
    '/profile-workspace',
    '/flows',
    '/settings',
  ]) {
    assert.equal(panelRouteTitleKey(path), 'nav.unknown');
  }

  assert.deepEqual(Object.keys(panelRouteMeta), ['home', 'setup', 'packs']);
});
