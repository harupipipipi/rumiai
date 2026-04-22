import assert from 'node:assert/strict';
import {beforeEach, test} from 'node:test';

import {apiFetch, bootstrapPanelSession} from './api.ts';

class MemoryStorage {
  private readonly values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  key(index: number): string | null {
    return Array.from(this.values.keys())[index] ?? null;
  }

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

type TestGlobals = typeof globalThis & {
  document?: Document;
  fetch?: typeof fetch;
  sessionStorage?: Storage;
  window?: Window & typeof globalThis;
};

const globals = globalThis as TestGlobals;

let lastFetchInit: RequestInit | undefined;
let lastFetchUrl = '';
let lastReplacedUrl = '';
let sessionStorageRef: MemoryStorage;

function installBrowser(href: string): MemoryStorage {
  const storage = new MemoryStorage();
  const window = {
    history: {
      replaceState: (_state: unknown, _title: string, url?: string | URL | null) => {
        const nextUrl = String(url ?? '');
        lastReplacedUrl = nextUrl;
        window.location.href = new URL(nextUrl, window.location.href).toString();
      },
    },
    location: {
      href,
    },
  };

  globals.document = {title: 'Rumi AI'} as unknown as Document;
  globals.sessionStorage = storage as unknown as Storage;
  globals.window = window as unknown as Window & typeof globalThis;
  sessionStorageRef = storage;
  return storage;
}

function installFetchMock(): void {
  globals.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    lastFetchUrl = String(input);
    lastFetchInit = init;

    if (lastFetchUrl === '/api/panel/auth/exchange') {
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
  }) as typeof fetch;
}

beforeEach(() => {
  lastFetchInit = undefined;
  lastFetchUrl = '';
  lastReplacedUrl = '';
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
  assert.equal(globals.window?.location.href, 'http://127.0.0.1:8765/panel/?v=42#ready');
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
