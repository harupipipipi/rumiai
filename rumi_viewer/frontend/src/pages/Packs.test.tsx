import assert from 'node:assert/strict';
import {afterEach, beforeEach, test} from 'node:test';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {MemoryRouter} from 'react-router-dom';
import {JSDOM} from 'jsdom';

import type {Pack, Toast} from '@/src/store';
import {useAppStore} from '@/src/store';
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

const refreshedDisabledPack = {
  pack_id: originalPack.id,
  name: originalPack.name,
  version: originalPack.version,
  description: originalPack.description,
  is_core: true,
  enabled: false,
  approval_status: 'approved',
  approved: true,
  hash_valid: true,
  critical_changed: false,
  approval_issues: [],
};

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

function packSwitch(): HTMLButtonElement {
  const element = container?.querySelector<HTMLButtonElement>(
    'button[role="switch"][aria-label="Toggle Defaults Pack"]',
  );
  assert.ok(element);
  return element;
}

function clickPackSwitch(): void {
  assert.ok(dom);
  packSwitch().dispatchEvent(new dom.window.MouseEvent('click', {
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
