import assert from 'node:assert/strict';
import {afterEach, beforeEach, test} from 'node:test';
import {JSDOM} from 'jsdom';

import {type Pack, useAppStore} from '@/src/store';
import type {ApiPackVMDoctor} from '@/src/lib/apiTypes';

const samplePack: Pack = {
  id: 'research-pack',
  name: 'Research Pack',
  version: '1.2.3',
  type: 'community',
  installed: true,
  enabled: true,
  description: 'Research tools',
  artifactDigest: 'sha256:research-artifact',
  profileId: 'profile-a',
  workspaceId: 'workspace-a',
  profileRevision: 'sha256:profile-a',
  planDigest: 'sha256:plan-a',
  catalogRevision: 'catalog-a',
  approvalStatus: 'approved',
  approvalReason: null,
  approved: true,
  hashValid: true,
  criticalChanged: false,
  approvalIssues: [],
  capabilities: [],
  flows: [],
  dependencies: [],
};

const healthyDoctor: ApiPackVMDoctor = {
  ready: true,
  backend_id: 'tobkiri.python-pack-v4',
  platform: 'macos',
  instance: 'tobkiri-packvm-v4',
  reason: null,
  attestation_digest: `sha256:${'a'.repeat(64)}`,
};

let dom: JSDOM | null = null;
let previousState: ReturnType<typeof useAppStore.getState>;
let originalFetch: typeof fetch;

beforeEach(() => {
  previousState = useAppStore.getState();
  originalFetch = globalThis.fetch;
  dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://localhost/panel/',
  });
  Object.defineProperties(globalThis, {
    window: {value: dom.window, configurable: true},
    document: {value: dom.window.document, configurable: true},
    navigator: {value: dom.window.navigator, configurable: true},
    localStorage: {value: dom.window.localStorage, configurable: true},
    sessionStorage: {value: dom.window.sessionStorage, configurable: true},
  });
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  useAppStore.setState(previousState, true);
  dom?.window.close();
  dom = null;
});

function binding() {
  return {
    profile_id: samplePack.profileId,
    workspace_id: samplePack.workspaceId,
    profile_revision: samplePack.profileRevision,
    plan_digest: samplePack.planDigest,
    catalog_revision: samplePack.catalogRevision,
  };
}

function catalogPack(enabled: boolean) {
  return {
    pack_id: samplePack.id,
    name: samplePack.name,
    version: samplePack.version,
    description: samplePack.description,
    is_core: false,
    installed: true,
    enabled,
    artifact_digest: samplePack.artifactDigest,
    approval_status: 'approved',
    approval_reason: null,
    approved: true,
    hash_valid: true,
    critical_changed: false,
    approval_issues: [],
    ...binding(),
  };
}

function dynamicCatalog() {
  return {
    version: 'rumi.ui.contribution.v1',
    profile_id: samplePack.profileId,
    profile_revision: samplePack.profileRevision,
    plan_hash: samplePack.planDigest,
    contributions: [],
    diagnostics: [],
    quarantined_pack_ids: [],
    catalog_hash: 'sha256:frontend-catalog',
  };
}

function installFetch(
  handler: (route: string, init?: RequestInit) => Promise<Response>,
): string[] {
  const routes: string[] = [];
  globalThis.fetch = (async (input, init) => {
    const url = String(input);
    const route = decodeURIComponent(url.replace('/api/contracts/defaultspack/', ''));
    routes.push(route);
    return handler(route, init);
  }) as typeof fetch;
  return routes;
}

function setStore(errors: string[]): void {
  useAppStore.setState({
    packs: [samplePack],
    packTogglePending: {},
    frontendCatalog: null,
    frontendCatalogError: null,
    packVmDoctor: healthyDoctor,
    addToast: (message, type) => {
      if (type === 'error') errors.push(message);
    },
  });
}

test('disable waits for the typed response, refreshes state, and survives a later catalog reload', async () => {
  let serverEnabled = true;
  const routes = installFetch(async (route, init) => {
    if (route === 'POST /api/pack-control/disable') {
      assert.deepEqual(JSON.parse(String(init?.body)), {pack_id: samplePack.id});
      serverEnabled = false;
      return new Response(JSON.stringify({
        success: true,
        data: {...binding(), pack_id: samplePack.id, enabled: false},
      }), {headers: {'Content-Type': 'application/json'}});
    }
    if (route === 'GET /api/pack-control/catalog') {
      return new Response(JSON.stringify({
        success: true,
        data: {...binding(), packs: [catalogPack(serverEnabled)], count: 1},
      }), {headers: {'Content-Type': 'application/json'}});
    }
    assert.equal(route, 'GET /api/ui/catalog');
    return new Response(JSON.stringify({success: true, data: {dynamic_host: dynamicCatalog()}}), {
      headers: {'Content-Type': 'application/json'},
    });
  });
  const errors: string[] = [];
  setStore(errors);

  assert.equal(await useAppStore.getState().togglePack(samplePack.id), true);
  assert.equal(useAppStore.getState().packs[0].enabled, false);
  assert.deepEqual(useAppStore.getState().packTogglePending, {});
  assert.deepEqual(errors, []);

  await useAppStore.getState().loadPacks();
  assert.equal(useAppStore.getState().packs[0].enabled, false);
  assert.equal(routes[0], 'POST /api/pack-control/disable');
  assert.deepEqual(routes.slice(1).sort(), [
    'GET /api/pack-control/catalog',
    'GET /api/pack-control/catalog',
    'GET /api/ui/catalog',
  ].sort());
});

test('disable denial leaves the Pack enabled, clears pending, and surfaces the server error', async () => {
  const routes = installFetch(async (route) => {
    assert.equal(route, 'POST /api/pack-control/disable');
    return new Response(JSON.stringify({
      success: false,
      data: null,
      error: 'HTTP 409 pack_disable_denied',
    }), {status: 409, headers: {'Content-Type': 'application/json'}});
  });
  const errors: string[] = [];
  setStore(errors);

  assert.equal(await useAppStore.getState().togglePack(samplePack.id), false);
  assert.equal(useAppStore.getState().packs[0].enabled, true);
  assert.deepEqual(useAppStore.getState().packTogglePending, {});
  assert.deepEqual(routes, ['POST /api/pack-control/disable']);
  assert.deepEqual(errors, ['HTTP 409 pack_disable_denied']);
});

test('disable timeout leaves the Pack enabled and does not leave a stuck switch', async () => {
  const routes = installFetch(async (route) => {
    assert.equal(route, 'POST /api/pack-control/disable');
    throw new Error('POST request timed out after 10000ms: /api/pack-control/disable');
  });
  const errors: string[] = [];
  setStore(errors);

  assert.equal(await useAppStore.getState().togglePack(samplePack.id), false);
  assert.equal(useAppStore.getState().packs[0].enabled, true);
  assert.deepEqual(useAppStore.getState().packTogglePending, {});
  assert.deepEqual(errors, ['POST request timed out after 10000ms: /api/pack-control/disable']);
});

test('a stale catalog response cannot re-enable a Pack after a confirmed disable', async () => {
  let catalogReads = 0;
  const routes = installFetch(async (route, init) => {
    if (route === 'POST /api/pack-control/disable') {
      assert.deepEqual(JSON.parse(String(init?.body)), {pack_id: samplePack.id});
      return new Response(JSON.stringify({
        success: true,
        data: {...binding(), pack_id: samplePack.id, enabled: false},
      }), {headers: {'Content-Type': 'application/json'}});
    }
    if (route === 'GET /api/pack-control/catalog') {
      catalogReads += 1;
      return new Response(JSON.stringify({
        success: true,
        data: {...binding(), packs: [catalogPack(catalogReads === 1)], count: 1},
      }), {headers: {'Content-Type': 'application/json'}});
    }
    assert.equal(route, 'GET /api/ui/catalog');
    return new Response(JSON.stringify({success: true, data: {dynamic_host: dynamicCatalog()}}), {
      headers: {'Content-Type': 'application/json'},
    });
  });
  const errors: string[] = [];
  setStore(errors);

  assert.equal(await useAppStore.getState().togglePack(samplePack.id), true);
  assert.equal(useAppStore.getState().packs[0].enabled, false);
  assert.equal(catalogReads, 1);
  assert.deepEqual(errors, []);
  assert.equal(routes[0], 'POST /api/pack-control/disable');
});

test('disable ignores a response for the wrong Pack or requested state', async () => {
  const routes = installFetch(async (route) => {
    assert.equal(route, 'POST /api/pack-control/disable');
    return new Response(JSON.stringify({
      success: true,
      data: {...binding(), pack_id: 'other-pack', enabled: true},
    }), {headers: {'Content-Type': 'application/json'}});
  });
  const errors: string[] = [];
  setStore(errors);

  assert.equal(await useAppStore.getState().togglePack(samplePack.id), false);
  assert.equal(useAppStore.getState().packs[0].enabled, true);
  assert.deepEqual(useAppStore.getState().packTogglePending, {});
  assert.deepEqual(routes, ['POST /api/pack-control/disable']);
  assert.deepEqual(errors, ['Tobkiri did not confirm the requested Pack state.']);
});

test('disable rejects a duplicate submission while the first request is pending', async () => {
  let release: (() => void) | undefined;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  const routes = installFetch(async (route, init) => {
    if (route === 'POST /api/pack-control/disable') {
      assert.deepEqual(JSON.parse(String(init?.body)), {pack_id: samplePack.id});
      await pending;
      return new Response(JSON.stringify({
        success: true,
        data: {...binding(), pack_id: samplePack.id, enabled: false},
      }), {headers: {'Content-Type': 'application/json'}});
    }
    if (route === 'GET /api/pack-control/catalog') {
      return new Response(JSON.stringify({
        success: true,
        data: {...binding(), packs: [catalogPack(false)], count: 1},
      }), {headers: {'Content-Type': 'application/json'}});
    }
    assert.fail(`unexpected route: ${route}`);
  });
  const errors: string[] = [];
  setStore(errors);

  const first = useAppStore.getState().togglePack(samplePack.id);
  assert.equal(useAppStore.getState().packTogglePending[samplePack.id], true);
  assert.equal(await useAppStore.getState().togglePack(samplePack.id), false);
  assert.deepEqual(routes, ['POST /api/pack-control/disable']);

  release?.();
  assert.equal(await first, true);
  assert.equal(useAppStore.getState().packs[0].enabled, false);
  assert.deepEqual(useAppStore.getState().packTogglePending, {});
  assert.deepEqual(errors, []);
});
