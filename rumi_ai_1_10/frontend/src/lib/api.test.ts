import assert from 'node:assert/strict';
import {beforeEach, test} from 'node:test';

import {apiFetch, bootstrapPanelSession, hasPendingPanelBootstrapCode} from './api.ts';

class MemoryStorage {
  private readonly values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.values.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, String(value));
  }
}

let lastFetchInit: RequestInit | undefined;
let lastFetchUrl = '';
let lastReplacedUrl = '';
let panelExchangeCount = 0;
let sessionStorageRef: MemoryStorage;

function installBrowser(href: string): MemoryStorage {
  const storage = new MemoryStorage();
  const windowMock = {
    history: {
      replaceState: (_state: unknown, _title: string, url?: string | URL | null) => {
        const nextUrl = String(url ?? '');
        lastReplacedUrl = nextUrl;
        windowMock.location.href = new URL(nextUrl, windowMock.location.href).toString();
      },
    },
    location: {
      href,
    },
  };

  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: { title: 'Rumi AI' } as Pick<Document, 'title'>,
    writable: true,
  });
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: storage as Storage,
    writable: true,
  });
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: windowMock as Pick<Window, 'history' | 'location'>,
    writable: true,
  });
  sessionStorageRef = storage;
  return storage;
}

function installFetchMock(): void {
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (async (input: string | URL | Request, init?: RequestInit) => {
      lastFetchUrl = String(input);
      lastFetchInit = init;

      if (lastFetchUrl === '/api/panel/auth/exchange') {
        panelExchangeCount += 1;
        return new Response(
          JSON.stringify({
            data: {csrf_token: 'csrf-from-server'},
            success: true,
          }),
          {
            headers: {'Content-Type': 'application/json'},
            status: 200,
          },
        );
      }

      return new Response(
        JSON.stringify({
          data: {ok: true},
          success: true,
        }),
        {
          headers: {'Content-Type': 'application/json'},
          status: 200,
        },
      );
    }) as typeof fetch,
    writable: true,
  });
}

beforeEach(() => {
  lastFetchInit = undefined;
  lastFetchUrl = '';
  lastReplacedUrl = '';
  panelExchangeCount = 0;
  installBrowser('http://127.0.0.1:8765/panel/');
  installFetchMock();
});

test('bootstrapPanelSession exchanges code and strips it from the URL', async () => {
  const storage = installBrowser('http://127.0.0.1:8765/panel/?code=one-time-code&v=42#ready');

  await bootstrapPanelSession();

  assert.equal(lastFetchUrl, '/api/panel/auth/exchange');
  assert.equal((lastFetchInit?.credentials as string | undefined), 'same-origin');
  assert.equal(storage.getItem('rumi-panel-csrf'), 'csrf-from-server');
  assert.equal(lastReplacedUrl, '/panel/?v=42#ready');
  assert.equal(window.location.href, 'http://127.0.0.1:8765/panel/?v=42#ready');
});

test('bootstrapPanelSession deduplicates concurrent exchanges for the same code', async () => {
  installBrowser('http://127.0.0.1:8765/panel/?code=one-time-code');

  await Promise.all([bootstrapPanelSession(), bootstrapPanelSession()]);

  assert.equal(panelExchangeCount, 1);
  assert.equal(sessionStorageRef.getItem('rumi-panel-csrf'), 'csrf-from-server');
});

test('hasPendingPanelBootstrapCode only reports true when the URL includes a code', () => {
  assert.equal(hasPendingPanelBootstrapCode('http://127.0.0.1:8765/panel/?code=abc'), true);
  assert.equal(hasPendingPanelBootstrapCode('http://127.0.0.1:8765/panel/'), false);
});

test('apiFetch adds the panel CSRF header for unsafe methods', async () => {
  installBrowser('http://127.0.0.1:8765/panel/?v=42');
  sessionStorageRef.setItem('rumi-panel-csrf', 'persisted-csrf');

  await apiFetch<{ok: boolean}>('/api/panel/flows', {method: 'POST', body: '{}'});

  assert.equal(lastFetchUrl, '/api/panel/flows');
  assert.equal(
    (lastFetchInit?.headers as Record<string, string>)?.['X-Rumi-CSRF'],
    'persisted-csrf',
  );
  assert.equal((lastFetchInit?.credentials as string | undefined), 'same-origin');
});

test('apiFetch waits for panel bootstrap before unsafe requests when code is pending', async () => {
  installBrowser('http://127.0.0.1:8765/panel/?code=one-time-code');

  await apiFetch<{ok: boolean}>('/api/panel/flows', {method: 'POST', body: '{}'});

  assert.equal(panelExchangeCount, 1);
  assert.equal(lastFetchUrl, '/api/panel/flows');
  assert.equal(
    (lastFetchInit?.headers as Record<string, string>)?.['X-Rumi-CSRF'],
    'csrf-from-server',
  );
  assert.equal(window.location.href, 'http://127.0.0.1:8765/panel/');
});

test('apiFetch leaves GET requests free of CSRF headers', async () => {
  installBrowser('http://127.0.0.1:8765/panel/?v=42');
  sessionStorageRef.setItem('rumi-panel-csrf', 'persisted-csrf');

  await apiFetch<{ok: boolean}>('/api/panel/dashboard');

  assert.equal(lastFetchUrl, '/api/panel/dashboard');
  assert.equal(
    (lastFetchInit?.headers as Record<string, string>)?.['X-Rumi-CSRF'],
    undefined,
  );
});

test('apiFetch waits for panel bootstrap before GET requests to panel APIs when code is pending', async () => {
  installBrowser('http://127.0.0.1:8765/panel/?code=one-time-code');

  await apiFetch<{ok: boolean}>('/api/panel/dashboard');

  assert.equal(panelExchangeCount, 1);
  assert.equal(lastFetchUrl, '/api/panel/dashboard');
  assert.equal(window.location.href, 'http://127.0.0.1:8765/panel/');
});

test('apiFetch does not bootstrap non-panel GET requests when code is pending', async () => {
  installBrowser('http://127.0.0.1:8765/panel/?code=one-time-code');

  await apiFetch<{ok: boolean}>('/health');

  assert.equal(panelExchangeCount, 0);
  assert.equal(lastFetchUrl, '/health');
  assert.equal(window.location.href, 'http://127.0.0.1:8765/panel/?code=one-time-code');
});

test('apiFetch deduplicates concurrent GET requests for the same URL', async () => {
  installBrowser('http://127.0.0.1:8765/panel/?v=42');

  let requestCount = 0;
  const pendingFetch = new Promise<Response>((resolve) => {
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: (async (input: string | URL | Request, init?: RequestInit) => {
        requestCount += 1;
        lastFetchUrl = String(input);
        lastFetchInit = init;
        return pendingFetch;
      }) as typeof fetch,
      writable: true,
    });

    queueMicrotask(() => {
      resolve(new Response(
        JSON.stringify({
          data: {ok: true},
          success: true,
        }),
        {
          headers: {'Content-Type': 'application/json'},
          status: 200,
        },
      ));
    });
  });

  const [first, second] = await Promise.all([
    apiFetch<{ok: boolean}>('/api/panel/flows'),
    apiFetch<{ok: boolean}>('/api/panel/flows'),
  ]);

  assert.equal(requestCount, 1);
  assert.deepEqual(first, {ok: true});
  assert.deepEqual(second, {ok: true});
});
