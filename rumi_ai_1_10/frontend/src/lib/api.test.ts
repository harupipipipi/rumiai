import assert from 'node:assert/strict';
import {beforeEach, test} from 'node:test';

import {apiFetch, bootstrapApiTokenFromLocation} from './api.ts';

class MemoryStorage {
  private readonly values = new Map<string, string>();

  clear(): void {
    this.values.clear();
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
  document?: {title: string};
  fetch?: typeof fetch;
  localStorage?: MemoryStorage;
  window?: {
    history: {
      replaceState: (_state: unknown, _title: string, url?: string | URL | null) => void;
    };
    localStorage: MemoryStorage;
    location: {
      href: string;
    };
  };
};

const globals = globalThis as TestGlobals;

let lastFetchInit: RequestInit | undefined;
let lastFetchUrl = '';
let lastReplacedUrl = '';

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
    localStorage: storage,
    location: {
      href,
    },
  };

  globals.document = {title: 'Rumi AI'};
  globals.localStorage = storage;
  globals.window = window;
  return storage;
}

function installFetchResponse(): void {
  globals.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    lastFetchUrl = String(input);
    lastFetchInit = init;

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
  installFetchResponse();
});

test('bootstrapApiTokenFromLocation persists token and strips it from the URL', () => {
  const storage = installBrowser('http://127.0.0.1:8765/panel/?token=panel-secret&v=42#ready');

  bootstrapApiTokenFromLocation();

  assert.equal(storage.getItem('rumi-api-token'), 'panel-secret');
  assert.equal(lastReplacedUrl, '/panel/?v=42#ready');
  assert.equal(globals.window?.location.href, 'http://127.0.0.1:8765/panel/?v=42#ready');
});

test('apiFetch injects an Authorization header from stored token state', async () => {
  const storage = installBrowser('http://127.0.0.1:8765/panel/?v=42');
  storage.setItem('rumi-api-token', 'persisted-token');

  await apiFetch<{ok: boolean}>('/api/panel/dashboard');

  assert.equal(lastFetchUrl, '/api/panel/dashboard');
  assert.equal(
    (lastFetchInit?.headers as Record<string, string>)?.Authorization,
    'Bearer persisted-token',
  );
});

test('apiFetch consumes a token directly from the current panel URL on first request', async () => {
  const storage = installBrowser('http://127.0.0.1:8765/panel/?token=fresh-token&v=77');

  await apiFetch<{ok: boolean}>('/api/panel/dashboard');

  assert.equal(storage.getItem('rumi-api-token'), 'fresh-token');
  assert.equal(lastReplacedUrl, '/panel/?v=77');
  assert.equal(
    (lastFetchInit?.headers as Record<string, string>)?.Authorization,
    'Bearer fresh-token',
  );
});
