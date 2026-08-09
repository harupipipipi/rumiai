import assert from 'node:assert/strict';
import {beforeEach, test} from 'node:test';

import {
  apiFetch,
  approvePack,
  bootstrapPanelSession,
  checkHealth,
  clearApiPrefetchCache,
  disablePack,
  enablePack,
  fetchDashboard,
  fetchFrontendCatalog,
  fetchPacks,
  fetchPresentationState,
  installPack,
  invokeFrontendCapability,
  launchSelectedPresentation,
  revokePackApproval,
  restartKernel,
  selectPresentation,
} from './api.ts';

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, String(value));
  }
}

let lastFetchUrl = '';
let lastFetchInit: RequestInit | undefined;
let exchangeCount = 0;
let presentationCatalogCount = 0;
let presentationSelection: Record<string, unknown> | undefined;
let presentationLaunchCount = 0;
let fetchHandler: ((input: string | URL | Request, init?: RequestInit) => Promise<Response>) | null = null;

function installBrowser(href = 'http://127.0.0.1:8765/panel/'): void {
  const storage = new MemoryStorage();
  const windowMock = {
    __TAURI__: {
      core: {
        invoke: async (command: string, args?: Record<string, unknown>) => {
          if (command === 'reauthorize_panel_session') return 'desktop-refresh-code';
          if (command === 'get_presentation_catalog') {
            presentationCatalogCount += 1;
            return {
              catalog: {base_packs: [], shell_providers: []},
              selection: null,
              materialization: {status: 'not_selected'},
            };
          }
          if (command === 'select_presentation') {
            presentationSelection = args?.selection as Record<string, unknown>;
            return {
              catalog: {base_packs: [], shell_providers: []},
              selection: args?.selection,
              materialization: {status: 'blocked'},
            };
          }
          if (command === 'launch_selected_presentation') {
            presentationLaunchCount += 1;
            return {
              status: 'launched',
              provider_id: 'shell.tauri.default',
              artifact_id: 'fixture-shell',
              message: 'fixture launched',
            };
          }
          return undefined;
        },
      },
    },
    history: {
      replaceState: (_state: unknown, _title: string, url?: string | URL | null) => {
        windowMock.location.href = new URL(String(url ?? ''), windowMock.location.href).toString();
      },
    },
    location: {href},
  };

  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: {title: 'Tobkiri'},
    writable: true,
  });
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: storage,
    writable: true,
  });
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: windowMock,
    writable: true,
  });
}

function installFetchMock(): void {
  fetchHandler = async (input, init) => {
    lastFetchUrl = String(input);
    lastFetchInit = init;
    if (lastFetchUrl === '/api/panel/auth/exchange') {
      exchangeCount += 1;
      return new Response(JSON.stringify({
        data: {csrf_token: 'csrf-from-server'},
        success: true,
      }), {headers: {'Content-Type': 'application/json'}});
    }
    const route = decodeURIComponent(lastFetchUrl.replace('/api/contracts/defaultspack/', ''));
    const data = route === 'POST /api/pack-control/approval-candidate'
      ? {candidate_id: 'candidate-one'}
      : route === 'GET /api/pack-control/catalog'
        ? {packs: [], count: 0}
        : {pack_id: 'pack-a', enabled: true, approved: true};
    return new Response(JSON.stringify({data, success: true}), {
      headers: {'Content-Type': 'application/json'},
    });
  };
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (async (input: string | URL | Request, init?: RequestInit) => {
      if (!fetchHandler) throw new Error('Missing fetch handler');
      return fetchHandler(input, init);
    }) as typeof fetch,
    writable: true,
  });
}

beforeEach(() => {
  clearApiPrefetchCache();
  lastFetchUrl = '';
  lastFetchInit = undefined;
  exchangeCount = 0;
  presentationCatalogCount = 0;
  presentationSelection = undefined;
  presentationLaunchCount = 0;
  installBrowser();
  installFetchMock();
});

test('Home and Packs use only exact v4 frontend contract routes', async () => {
  const operations: string[] = [];
  fetchHandler = async (input, init) => {
    lastFetchUrl = String(input);
    lastFetchInit = init;
    const route = decodeURIComponent(lastFetchUrl.replace('/api/contracts/defaultspack/', ''));
    operations.push(route);
    const data = route === 'POST /api/pack-control/approval-candidate'
      ? {candidate_id: 'candidate-one'}
      : route === 'GET /api/pack-control/catalog'
        ? {packs: [], count: 0}
        : {pack_id: 'pack-a', enabled: true, approved: true};
    return new Response(JSON.stringify({data, success: true}), {
      headers: {'Content-Type': 'application/json'},
    });
  };

  await fetchDashboard();
  await fetchPacks();
  await installPack('pack-a');
  await approvePack('pack-a');
  await enablePack('pack-a');
  await disablePack('pack-a');

  assert.deepEqual(operations, [
    'GET /api/home/dashboard',
    'GET /api/pack-control/catalog',
    'POST /api/pack-control/install',
    'POST /api/pack-control/approval-candidate',
    'POST /api/pack-control/approval-approve',
    'POST /api/pack-control/enable',
    'POST /api/pack-control/disable',
  ]);
  assert.equal(lastFetchInit?.method, 'POST');
});

test('dynamic catalog and capability invocation use the exact canonical v4 routes', async () => {
  const operations: string[] = [];
  let invocationBody: Record<string, unknown> | undefined;
  fetchHandler = async (input, init) => {
    lastFetchUrl = String(input);
    lastFetchInit = init;
    const route = decodeURIComponent(lastFetchUrl.replace('/api/contracts/defaultspack/', ''));
    operations.push(route);
    if (route === 'POST /api/ui/capability/invoke') {
      invocationBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return new Response(JSON.stringify({success: true, data: {kind: 'stat', size: 12}}), {
        headers: {'Content-Type': 'application/json'},
      });
    }
    return new Response(JSON.stringify({
      success: true,
      data: {
        dynamic_host: {
          version: 'rumi.ui.contribution.v1',
          profile_id: 'profile-a',
          profile_revision: 'sha256:profile-a',
          plan_hash: 'sha256:plan-a',
          contributions: [{
            contribution_id: 'file-inspect',
            owner_pack_id: 'rumi_file_inspect_pack',
            label: 'rumi_file_inspect_pack.file-inspect',
            action_contract: 'tobkiri.service.file.inspect.v1',
            operation_id: 'rumi_file_inspect_pack.file-inspect',
          }],
          diagnostics: [],
          quarantined_pack_ids: [],
          catalog_hash: 'sha256:catalog-a',
        },
      },
    }), {headers: {'Content-Type': 'application/json'}});
  };

  const catalog = await fetchFrontendCatalog();
  const result = await invokeFrontendCapability({
    profileId: catalog.profile_id,
    planHash: catalog.plan_hash,
    catalogHash: catalog.catalog_hash,
    contributionId: 'file-inspect',
    ownerPackId: 'rumi_file_inspect_pack',
    contractId: 'tobkiri.service.file.inspect.v1',
    payload: {name: 'stat', path: 'docs/example.txt'},
  });

  assert.deepEqual(operations, [
    'GET /api/ui/catalog',
    'POST /api/ui/capability/invoke',
  ]);
  assert.equal(typeof invocationBody?.request_id, 'string');
  assert.equal(typeof invocationBody?.expires_at, 'number');
  assert.deepEqual(invocationBody, {
    request_id: invocationBody?.request_id,
    expires_at: invocationBody?.expires_at,
    profile_id: 'profile-a',
    plan_hash: 'sha256:plan-a',
    catalog_hash: 'sha256:catalog-a',
    contribution_id: 'file-inspect',
    owner_pack_id: 'rumi_file_inspect_pack',
    contract_id: 'tobkiri.service.file.inspect.v1',
    payload: {name: 'stat', path: 'docs/example.txt'},
  });
  assert.deepEqual(result, {kind: 'stat', size: 12});
  assert.doesNotMatch(lastFetchUrl, /api\/v4\/dispatch/);
});

test('approval revocation uses the exact typed v4 contract route and payload', async () => {
  fetchHandler = async (input, init) => {
    lastFetchUrl = String(input);
    lastFetchInit = init;
    return new Response(JSON.stringify({
      data: {
        pack_id: 'pack-a',
        approved: false,
        enabled: false,
        approval_status: 'revoked',
      },
      success: true,
    }), {headers: {'Content-Type': 'application/json'}});
  };

  const response = await revokePackApproval('pack-a');

  assert.equal(
    decodeURIComponent(lastFetchUrl.replace('/api/contracts/defaultspack/', '')),
    'POST /api/pack-control/approval-revoke',
  );
  assert.deepEqual(JSON.parse(String(lastFetchInit?.body)), {pack_id: 'pack-a'});
  assert.deepEqual(response, {
    pack_id: 'pack-a',
    approved: false,
    enabled: false,
    approval_status: 'revoked',
  });
});

test('kernel restart uses the exact typed v4 contract route', async () => {
  fetchHandler = async (input, init) => {
    lastFetchUrl = String(input);
    lastFetchInit = init;
    return new Response(JSON.stringify({
      data: {restarting: true, message: 'Kernel restart requested.'},
      success: true,
    }), {headers: {'Content-Type': 'application/json'}});
  };

  const response = await restartKernel();

  assert.equal(
    decodeURIComponent(lastFetchUrl.replace('/api/contracts/defaultspack/', '')),
    'POST /api/pack-control/restart',
  );
  assert.equal(lastFetchInit?.method, 'POST');
  assert.deepEqual(JSON.parse(String(lastFetchInit?.body)), {});
  assert.deepEqual(response, {restarting: true, message: 'Kernel restart requested.'});
});

test('v4 contract failure is surfaced and never treated as a successful fallback', async () => {
  fetchHandler = async (input) => {
    lastFetchUrl = String(input);
    return new Response(JSON.stringify({success: false, data: null, error: 'retired'}), {status: 410});
  };

  await assert.rejects(fetchPacks(), /retired/);
  assert.match(lastFetchUrl, /^\/api\/contracts\/defaultspack\//);
});

test('unsafe frontend requests time out and reject instead of leaving lifecycle controls pending', async () => {
  fetchHandler = async () => new Promise<Response>(() => {});

  await assert.rejects(
    apiFetch('/api/pack-control/disable', {method: 'POST'}, {timeoutMs: 1}),
    /POST request timed out after 1ms: \/api\/pack-control\/disable/,
  );
});

test('presentation wrappers use Launcher-owned Tauri commands', async () => {
  await fetchPresentationState();
  await selectPresentation({
    base_pack_id: 'defaults-basepack',
    shell_provider_id: 'shell.tauri.default',
  });
  const result = await launchSelectedPresentation();

  assert.equal(presentationCatalogCount, 1);
  assert.deepEqual(presentationSelection, {
    base_pack_id: 'defaults-basepack',
    shell_provider_id: 'shell.tauri.default',
  });
  assert.equal(presentationLaunchCount, 1);
  assert.equal(result.status, 'launched');
});

test('presentation wrappers fail closed outside Launcher instead of using a retired HTTP route', async () => {
  const windowValue = window as Window & {__TAURI__?: unknown; __TAURI_INTERNALS__?: unknown};
  delete windowValue.__TAURI__;
  delete windowValue.__TAURI_INTERNALS__;

  await assert.rejects(fetchPresentationState(), /only available in Tobkiri Launcher/);
  assert.equal(lastFetchUrl, '');
});

test('panel bootstrap exchanges its session code before setup requests', async () => {
  installBrowser('http://127.0.0.1:8765/panel/setup?code=one-time-code');
  installFetchMock();

  await bootstrapPanelSession();

  assert.equal(exchangeCount, 1);
  assert.equal(lastFetchUrl, '/api/panel/auth/exchange');
  assert.equal(window.location.href, 'http://127.0.0.1:8765/panel/setup');
});

test('setup and health requests remain separate from Pack contract dispatch', async () => {
  await apiFetch('/api/setup/packs');
  assert.equal(lastFetchUrl, '/api/setup/packs');
  await checkHealth();
  assert.equal(lastFetchUrl, '/health');
});
