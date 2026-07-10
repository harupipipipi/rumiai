import assert from 'node:assert/strict';
import {afterEach, beforeEach, test} from 'node:test';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {JSDOM} from 'jsdom';

import type {Pack, Toast} from '@/src/store';
import {useAppStore} from '@/src/store';
import {PackDetail} from './PackDetail';
import {Packs} from './Packs';

interface Deferred<T> {
  promise: Promise<T>;
  reject: (reason?: unknown) => void;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let reject!: Deferred<T>['reject'];
  let resolve!: Deferred<T>['resolve'];
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return {promise, reject, resolve};
}

const originalPack: Pack = {
  id: 'defaultspack',
  name: 'Defaults Pack',
  version: '1.0.0',
  type: 'core',
  enabled: true,
  description: 'Built-in capabilities',
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

const secondPack: Pack = {
  ...originalPack,
  id: 'communitypack',
  name: 'Community Pack',
  type: 'community',
};

function apiPack(pack: Pack, enabled: boolean) {
  return {
    pack_id: pack.id,
    name: pack.name,
    version: pack.version,
    description: pack.description,
    is_core: pack.type === 'core',
    enabled,
    approval_status: 'approved',
    approved: true,
    hash_valid: true,
    critical_changed: false,
    approval_issues: [],
  };
}

const refreshedDisabledPack = apiPack(originalPack, false);

const storeLoadPacks = useAppStore.getState().loadPacks;
const storeTogglePack = useAppStore.getState().togglePack;
let feedback: Array<Pick<Toast, 'message' | 'type'>> = [];
let container: HTMLDivElement | null = null;
let dom: JSDOM | null = null;
let root: Root | null = null;

function successfulResponse(data: unknown): Response {
  return new Response(JSON.stringify({success: true, data, error: null}), {
    headers: {'Content-Type': 'application/json'},
    status: 200,
  });
}

async function settlePromises(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

async function renderPacks(): Promise<void> {
  assert.ok(root);
  await act(async () => {
    root?.render(
      <MemoryRouter initialEntries={['/packs']}>
        <Packs />
      </MemoryRouter>,
    );
    await settlePromises();
  });
}

async function renderPackDetail(): Promise<void> {
  assert.ok(root);
  await act(async () => {
    root?.render(
      <MemoryRouter initialEntries={[`/packs/${originalPack.id}`]}>
        <Routes>
          <Route path="/packs/:id" element={<PackDetail />} />
        </Routes>
      </MemoryRouter>,
    );
    await settlePromises();
  });
}

async function replacePacksWithPackDetail(): Promise<void> {
  assert.ok(container);
  assert.ok(root);
  await act(async () => {
    root?.unmount();
  });
  root = createRoot(container);
  await renderPackDetail();
}

function packSwitch(name = originalPack.name): HTMLButtonElement {
  const element = container?.querySelector<HTMLButtonElement>(
    `button[role="switch"][aria-label="Toggle ${name}"]`,
  );
  assert.ok(element);
  return element;
}

function clickPackSwitch(name = originalPack.name): void {
  assert.ok(dom);
  packSwitch(name).dispatchEvent(new dom.window.MouseEvent('click', {
    bubbles: true,
    cancelable: true,
  }));
}

beforeEach(() => {
  dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://127.0.0.1:8765/panel/packs',
  });
  Object.defineProperty(globalThis, 'IS_REACT_ACT_ENVIRONMENT', {
    configurable: true,
    value: true,
    writable: true,
  });
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: dom.window.sessionStorage,
    writable: true,
  });
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: dom.window,
    writable: true,
  });
  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: dom.window.document,
    writable: true,
  });
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: dom.window.navigator,
    writable: true,
  });

  feedback = [];
  container = dom.window.document.querySelector<HTMLDivElement>('#root');
  assert.ok(container);
  root = createRoot(container);
  useAppStore.setState({
    addToast: (message, type) => feedback.push({message, type}),
    apiError: null,
    isLoading: false,
    loadPacks: async () => {},
    packs: [{...originalPack}],
    pendingPackIds: [],
    profile: {...useAppStore.getState().profile, language: 'en'},
    toasts: [],
    togglePack: storeTogglePack,
  });
});

afterEach(async () => {
  if (root) {
    await act(async () => {
      root?.unmount();
    });
  }
  dom?.window.close();
  container = null;
  dom = null;
  root = null;
});

test('Packs blocks rapid duplicate toggles and preserves state after a rejected write', async () => {
  const request = deferred<Response>();
  let fetchCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: () => {
      fetchCalls += 1;
      return request.promise;
    },
    writable: true,
  });

  await renderPacks();
  await act(async () => {
    clickPackSwitch();
    await settlePromises();
  });

  assert.equal(fetchCalls, 1);
  assert.equal(packSwitch().disabled, true);
  assert.equal(packSwitch().getAttribute('aria-busy'), 'true');

  await act(async () => {
    clickPackSwitch();
    clickPackSwitch();
    await settlePromises();
  });
  assert.equal(fetchCalls, 1);

  await act(async () => {
    request.reject(new Error('toggle rejected'));
    await settlePromises();
  });

  assert.equal(packSwitch().disabled, false);
  assert.equal(packSwitch().getAttribute('aria-busy'), 'false');
  assert.equal(packSwitch().getAttribute('aria-checked'), 'true');
  assert.equal(useAppStore.getState().packs[0]?.enabled, true);
  assert.deepEqual(feedback, [{message: 'toggle rejected', type: 'error'}]);
});

test('Packs stays pending through refresh failure and emits only the error result', async () => {
  const refresh = deferred<Response>();
  let fetchCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: () => {
      fetchCalls += 1;
      if (fetchCalls === 1) {
        return Promise.resolve(successfulResponse({
          pack_id: originalPack.id,
          enabled: false,
        }));
      }
      return refresh.promise;
    },
    writable: true,
  });

  await renderPacks();
  await act(async () => {
    clickPackSwitch();
    await settlePromises();
  });

  assert.equal(fetchCalls, 2);
  assert.equal(packSwitch().disabled, true);
  assert.equal(packSwitch().getAttribute('aria-busy'), 'true');

  await act(async () => {
    clickPackSwitch();
    await settlePromises();
  });
  assert.equal(fetchCalls, 2);

  await act(async () => {
    refresh.reject(new Error('refresh rejected'));
    await settlePromises();
  });

  assert.equal(packSwitch().disabled, false);
  assert.equal(packSwitch().getAttribute('aria-checked'), 'true');
  assert.equal(useAppStore.getState().packs[0]?.enabled, true);
  assert.deepEqual(feedback, [{message: 'refresh rejected', type: 'error'}]);
});

test('Packs confirms a successful toggle exactly once after refresh completes', async () => {
  const refresh = deferred<Response>();
  let fetchCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: () => {
      fetchCalls += 1;
      if (fetchCalls === 1) {
        return Promise.resolve(successfulResponse({
          pack_id: originalPack.id,
          enabled: false,
        }));
      }
      return refresh.promise;
    },
    writable: true,
  });

  await renderPacks();
  await act(async () => {
    clickPackSwitch();
    await settlePromises();
  });

  assert.equal(fetchCalls, 2);
  assert.equal(packSwitch().disabled, true);
  assert.deepEqual(feedback, []);

  await act(async () => {
    refresh.resolve(successfulResponse({
      packs: [refreshedDisabledPack],
      count: 1,
    }));
    await settlePromises();
  });

  assert.equal(packSwitch().disabled, false);
  assert.equal(packSwitch().getAttribute('aria-busy'), 'false');
  assert.equal(packSwitch().getAttribute('aria-checked'), 'false');
  assert.equal(useAppStore.getState().packs[0]?.enabled, false);
  assert.deepEqual(feedback, [{message: 'Defaults Pack disabled', type: 'success'}]);
});

test('Packs serializes different pack mutations through separate fresh refreshes', async () => {
  const firstPost = deferred<Response>();
  const firstRefresh = deferred<Response>();
  const secondPost = deferred<Response>();
  const secondRefresh = deferred<Response>();
  const requests: string[] = [];
  let refreshCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      requests.push(`${method} ${path}`);
      if (method === 'POST' && path.endsWith(`/${originalPack.id}/disable`)) {
        return firstPost.promise;
      }
      if (method === 'POST' && path.endsWith(`/${secondPack.id}/disable`)) {
        return secondPost.promise;
      }
      if (method === 'GET' && path.endsWith('/api/panel/packs')) {
        refreshCalls += 1;
        return refreshCalls === 1 ? firstRefresh.promise : secondRefresh.promise;
      }
      return Promise.reject(new Error(`Unexpected request: ${method} ${path}`));
    },
    writable: true,
  });
  useAppStore.setState({packs: [{...originalPack}, {...secondPack}]});

  await renderPacks();
  await act(async () => {
    clickPackSwitch(originalPack.name);
    await settlePromises();
  });
  await act(async () => {
    clickPackSwitch(secondPack.name);
    await settlePromises();
  });

  assert.deepEqual(requests, [
    `POST /api/panel/packs/${originalPack.id}/disable`,
  ]);
  assert.equal(packSwitch(originalPack.name).disabled, true);
  assert.equal(packSwitch(secondPack.name).disabled, true);

  await act(async () => {
    firstPost.resolve(successfulResponse({pack_id: originalPack.id, enabled: false}));
    await settlePromises();
  });
  assert.deepEqual(requests, [
    `POST /api/panel/packs/${originalPack.id}/disable`,
    'GET /api/panel/packs',
  ]);

  await act(async () => {
    firstRefresh.resolve(successfulResponse({
      packs: [apiPack(originalPack, false), apiPack(secondPack, true)],
      count: 2,
    }));
    await settlePromises();
  });
  assert.deepEqual(requests, [
    `POST /api/panel/packs/${originalPack.id}/disable`,
    'GET /api/panel/packs',
    `POST /api/panel/packs/${secondPack.id}/disable`,
  ]);
  assert.equal(packSwitch(originalPack.name).disabled, false);
  assert.equal(packSwitch(secondPack.name).disabled, true);
  assert.deepEqual(useAppStore.getState().packs.map((pack) => pack.enabled), [false, true]);
  assert.deepEqual(feedback, [{message: 'Defaults Pack disabled', type: 'success'}]);

  await act(async () => {
    secondPost.resolve(successfulResponse({pack_id: secondPack.id, enabled: false}));
    await settlePromises();
  });
  assert.deepEqual(requests, [
    `POST /api/panel/packs/${originalPack.id}/disable`,
    'GET /api/panel/packs',
    `POST /api/panel/packs/${secondPack.id}/disable`,
    'GET /api/panel/packs',
  ]);

  await act(async () => {
    secondRefresh.resolve(successfulResponse({
      packs: [apiPack(originalPack, false), apiPack(secondPack, false)],
      count: 2,
    }));
    await settlePromises();
  });

  assert.equal(packSwitch(originalPack.name).getAttribute('aria-checked'), 'false');
  assert.equal(packSwitch(secondPack.name).getAttribute('aria-checked'), 'false');
  assert.equal(packSwitch(secondPack.name).disabled, false);
  assert.deepEqual(useAppStore.getState().packs.map((pack) => pack.enabled), [false, false]);
  assert.deepEqual(feedback, [
    {message: 'Defaults Pack disabled', type: 'success'},
    {message: 'Community Pack disabled', type: 'success'},
  ]);
});

test('Packs confirms against a fresh post-write GET and ignores the late mount response', async () => {
  const staleMountRead = deferred<Response>();
  const freshMutationRead = deferred<Response>();
  const requests: string[] = [];
  let getCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      requests.push(`${method} ${path}`);
      if (method === 'POST') {
        return Promise.resolve(successfulResponse({
          pack_id: originalPack.id,
          enabled: false,
        }));
      }
      getCalls += 1;
      return getCalls === 1 ? staleMountRead.promise : freshMutationRead.promise;
    },
    writable: true,
  });
  useAppStore.setState({loadPacks: storeLoadPacks});

  await renderPacks();
  assert.deepEqual(requests, ['GET /api/panel/packs']);

  await act(async () => {
    clickPackSwitch();
    await settlePromises();
  });
  assert.deepEqual(requests, [
    'GET /api/panel/packs',
    `POST /api/panel/packs/${originalPack.id}/disable`,
    'GET /api/panel/packs',
  ]);
  assert.equal(packSwitch().disabled, true);

  await act(async () => {
    freshMutationRead.resolve(successfulResponse({
      packs: [apiPack(originalPack, false)],
      count: 1,
    }));
    await settlePromises();
  });
  assert.equal(packSwitch().getAttribute('aria-checked'), 'false');
  assert.deepEqual(feedback, [{message: 'Defaults Pack disabled', type: 'success'}]);

  await act(async () => {
    staleMountRead.resolve(successfulResponse({
      packs: [apiPack(originalPack, true)],
      count: 1,
    }));
    await settlePromises();
  });

  assert.equal(packSwitch().getAttribute('aria-checked'), 'false');
  assert.equal(useAppStore.getState().packs[0]?.enabled, false);
  assert.equal(useAppStore.getState().isLoading, false);
  assert.deepEqual(feedback, [{message: 'Defaults Pack disabled', type: 'success'}]);
});

test('Packs rejects a fresh enabled-state mismatch while displaying server truth', async () => {
  const requests: string[] = [];
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      requests.push(`${method} ${String(input)}`);
      if (method === 'POST') {
        return Promise.resolve(successfulResponse({
          pack_id: originalPack.id,
          enabled: false,
        }));
      }
      return Promise.resolve(successfulResponse({
        packs: [apiPack(originalPack, true)],
        count: 1,
      }));
    },
    writable: true,
  });

  await renderPacks();
  await act(async () => {
    clickPackSwitch();
    await settlePromises();
  });

  assert.deepEqual(requests, [
    `POST /api/panel/packs/${originalPack.id}/disable`,
    'GET /api/panel/packs',
  ]);
  assert.equal(packSwitch().getAttribute('aria-checked'), 'true');
  assert.equal(useAppStore.getState().packs[0]?.enabled, true);
  assert.deepEqual(feedback, [{message: 'Pack update was not confirmed', type: 'error'}]);
});

test('Packs rejects a missing confirmation target while displaying the fresh list', async () => {
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (_input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      if (init?.method === 'POST') {
        return Promise.resolve(successfulResponse({
          pack_id: originalPack.id,
          enabled: false,
        }));
      }
      return Promise.resolve(successfulResponse({packs: [], count: 0}));
    },
    writable: true,
  });

  await renderPacks();
  await act(async () => {
    clickPackSwitch();
    await settlePromises();
  });

  assert.deepEqual(useAppStore.getState().packs, []);
  assert.equal(container?.querySelector('button[role="switch"]'), null);
  assert.match(container?.textContent ?? '', /No packs found/);
  assert.deepEqual(feedback, [{message: 'Pack update was not confirmed', type: 'error'}]);
});

test('Pack pending state survives remount into PackDetail and blocks the inverse toggle', async () => {
  const post = deferred<Response>();
  const refresh = deferred<Response>();
  const requests: string[] = [];
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      requests.push(`${method} ${path}`);
      return method === 'POST' ? post.promise : refresh.promise;
    },
    writable: true,
  });

  await renderPacks();
  await act(async () => {
    clickPackSwitch();
    await settlePromises();
  });
  assert.deepEqual(useAppStore.getState().pendingPackIds, [originalPack.id]);
  assert.deepEqual(requests, [`POST /api/panel/packs/${originalPack.id}/disable`]);

  await replacePacksWithPackDetail();
  assert.equal(packSwitch().disabled, true);
  assert.equal(packSwitch().getAttribute('aria-busy'), 'true');

  await act(async () => {
    clickPackSwitch();
    await settlePromises();
  });
  assert.deepEqual(requests, [`POST /api/panel/packs/${originalPack.id}/disable`]);
  assert.deepEqual(
    await useAppStore.getState().togglePack(originalPack.id),
    {ok: false, error: 'Pack update already in progress'},
  );

  await act(async () => {
    post.resolve(successfulResponse({pack_id: originalPack.id, enabled: false}));
    await settlePromises();
  });
  assert.deepEqual(requests, [
    `POST /api/panel/packs/${originalPack.id}/disable`,
    'GET /api/panel/packs',
  ]);
  assert.equal(packSwitch().disabled, true);

  await act(async () => {
    refresh.resolve(successfulResponse({
      packs: [apiPack(originalPack, false)],
      count: 1,
    }));
    await settlePromises();
  });

  assert.equal(packSwitch().disabled, false);
  assert.equal(packSwitch().getAttribute('aria-busy'), 'false');
  assert.equal(packSwitch().getAttribute('aria-checked'), 'false');
  assert.deepEqual(useAppStore.getState().pendingPackIds, []);
  assert.deepEqual(feedback, [{message: 'Defaults Pack disabled', type: 'success'}]);
});

test('PackDetail keeps confirmed state and emits one error after a rejected write', async () => {
  const post = deferred<Response>();
  let postCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (_input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      assert.equal(init?.method, 'POST');
      postCalls += 1;
      return post.promise;
    },
    writable: true,
  });

  await renderPackDetail();
  await act(async () => {
    clickPackSwitch();
    await settlePromises();
  });
  assert.equal(postCalls, 1);
  assert.equal(packSwitch().disabled, true);
  assert.equal(packSwitch().getAttribute('aria-busy'), 'true');

  await act(async () => {
    clickPackSwitch();
    await settlePromises();
  });
  assert.equal(postCalls, 1);

  await act(async () => {
    post.reject(new Error('detail toggle rejected'));
    await settlePromises();
  });

  assert.equal(packSwitch().disabled, false);
  assert.equal(packSwitch().getAttribute('aria-busy'), 'false');
  assert.equal(packSwitch().getAttribute('aria-checked'), 'true');
  assert.equal(useAppStore.getState().packs[0]?.enabled, true);
  assert.deepEqual(feedback, [{message: 'detail toggle rejected', type: 'error'}]);
});
