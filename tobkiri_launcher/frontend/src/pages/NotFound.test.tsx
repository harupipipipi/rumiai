import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';
import { MemoryRouter, Route, Routes } from 'react-router';

import { useAppStore } from '@/src/store';
import { NotFound } from './NotFound';

const appSource = readFileSync(resolve(import.meta.dirname, '../App.tsx'), 'utf8');

test('the production panel route tree registers the unknown-route state', () => {
  assert.match(appSource, /import \{ NotFound \} from '@\/src\/pages\/NotFound'/);
  assert.match(appSource, /<Route path="\*" element=\{<NotFound \/>\} \/>/);
});

async function renderUnknown(
  path: string,
  language = 'en',
  clipboardRejects = false,
) {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', {
    url: `http://localhost${path}`,
  });
  const copied: string[] = [];
  Object.defineProperty(dom.window.navigator, 'clipboard', {
    value: {
      writeText: async (value: string) => {
        if (clipboardRejects) throw new Error('Clipboard permission denied');
        copied.push(value);
      },
    },
    configurable: true,
  });
  Object.defineProperties(globalThis, {
    window: { value: dom.window, configurable: true },
    document: { value: dom.window.document, configurable: true },
    navigator: { value: dom.window.navigator, configurable: true },
    IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
  });
  useAppStore.setState((state) => ({
    profile: { ...state.profile, language },
  }));
  const root = createRoot(document.getElementById('root')!);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<p>Home reached</p>} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </MemoryRouter>,
    );
  });
  return { copied, dom, root };
}

for (const path of [
  '/stale-bookmark',
  '/setup/callback/expired',
  '/packs/example/nested/unknown',
]) {
  test(`unknown route ${path} renders a distinct recovery state`, async () => {
    const {dom, root} = await renderUnknown(path);
    try {
      assert.match(document.body.textContent ?? '', /Page not found/);
      assert.match(document.body.textContent ?? '', /Unknown destination/);
      assert.doesNotMatch(
        document.body.textContent ?? '',
        /Loading|Offline|Unauthorized/,
      );
      const details = document.querySelector('details');
      assert.ok(details);
      assert.equal(details.open, false);
      assert.equal(details.querySelector('code')?.textContent, path);
      assert.ok(
        document.querySelector('button[aria-label="Copy requested path"]'),
      );
    } finally {
      await act(async () => root.unmount());
      dom.window.close();
    }
  });
}

test('recovery copy is localized and keeps the requested path secondary', async () => {
  const path = '/missing?source=bookmark#old';
  const {copied, dom, root} = await renderUnknown(path, 'ja');
  try {
    assert.match(
      document.body.textContent ?? '',
      /\u30da\u30fc\u30b8\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093/,
    );
    const details = document.querySelector('details')!;
    assert.equal(details.open, false);
    details.open = true;
    const copyButton = document.querySelector<HTMLButtonElement>(
      'button[aria-label="\u8981\u6c42\u3055\u308c\u305f\u30d1\u30b9\u3092\u30b3\u30d4\u30fc"]',
    )!;
    await act(async () => copyButton.click());
    assert.deepEqual(copied, [path]);
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
  }
});

test('copy falls back to a temporary selection when Clipboard API is denied', async () => {
  const {dom, root} = await renderUnknown('/clipboard-fallback', 'en', true);
  const copied: string[] = [];
  Object.defineProperty(document, 'execCommand', {
    value: (command: string) => {
      assert.equal(command, 'copy');
      copied.push(document.querySelector<HTMLTextAreaElement>('textarea')!.value);
      return true;
    },
    configurable: true,
  });
  try {
    const copyButton = document.querySelector<HTMLButtonElement>(
      'button[aria-label="Copy requested path"]',
    )!;
    await act(async () => {
      copyButton.click();
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    assert.deepEqual(copied, ['/clipboard-fallback']);
    assert.ok(document.querySelector('button[aria-label="Path copied"]'));
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
  }
});

test('Home recovery action returns to the panel home route', async () => {
  const {dom, root} = await renderUnknown('/no-longer-here');
  try {
    const homeButton = [...document.querySelectorAll('button')].find(
      (button) => button.textContent?.includes('Go to Home'),
    );
    assert.ok(homeButton);
    await act(async () => homeButton.click());
    assert.match(document.body.textContent ?? '', /Home reached/);
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
  }
});
