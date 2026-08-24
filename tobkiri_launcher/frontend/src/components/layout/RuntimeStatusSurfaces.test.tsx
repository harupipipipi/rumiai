import assert from 'node:assert/strict';
import test from 'node:test';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {MemoryRouter, Route, Routes} from 'react-router';

import {useAppStore} from '@/src/store';
import {translate, type Locale} from '@/src/lib/i18n';
import {copyRuntimeDetails, Layout} from './Layout';

type RuntimeScenario = 'runtime_ready' | 'starting' | 'error';

const GLOBAL_KEYS = [
  'window',
  'document',
  'navigator',
  'localStorage',
  'IS_REACT_ACT_ENVIRONMENT',
] as const;

type GlobalKey = (typeof GLOBAL_KEYS)[number];
type GlobalSnapshot = {[key in GlobalKey]: PropertyDescriptor | undefined};

function captureGlobals(): GlobalSnapshot {
  return Object.fromEntries(
    GLOBAL_KEYS.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
  ) as GlobalSnapshot;
}

function restoreGlobals(snapshot: GlobalSnapshot): void {
  for (const key of GLOBAL_KEYS) {
    const descriptor = snapshot[key];
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else Reflect.deleteProperty(globalThis, key);
  }
}

async function renderRuntime(
  status: RuntimeScenario,
  error: string | null = null,
  disconnected = false,
): Promise<{dom: JSDOM; root: Root; restore: () => Promise<void>}> {
  const globals = captureGlobals();
  const previousState = useAppStore.getState();
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/panel/packs',
  });
  Object.defineProperties(globalThis, {
    window: {value: dom.window, configurable: true},
    document: {value: dom.window.document, configurable: true},
    navigator: {value: dom.window.navigator, configurable: true},
    localStorage: {value: dom.window.localStorage, configurable: true},
    IS_REACT_ACT_ENVIRONMENT: {value: true, configurable: true},
  });
  useAppStore.setState({
    isSetupDone: true,
    runtimeReady: status === 'runtime_ready',
    runtimeStatus: status,
    runtimeError: error,
    runtimeDisconnected: disconnected,
  });
  const rootElement = document.getElementById('root');
  assert.ok(rootElement);
  const root = createRoot(rootElement);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/packs']}>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route path="packs" element={<p>Pack page</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
  });
  return {
    dom,
    root,
    restore: async () => {
      await act(async () => root.unmount());
      useAppStore.setState(previousState, true);
      dom.window.close();
      restoreGlobals(globals);
    },
  };
}

test('healthy runtime has one compact polite status and no banner', {concurrency: false}, async () => {
  const surface = await renderRuntime('runtime_ready');
  try {
    assert.equal(document.querySelectorAll('[role="status"][aria-live="polite"]').length, 1);
    assert.equal(document.querySelector('[data-runtime-status]'), null);
    assert.equal(document.querySelector('[role="alert"]'), null);
    assert.equal((document.body.textContent ?? '').match(/Runtime ready/g)?.length, 1);
  } finally {
    await surface.restore();
  }
});

test('warming runtime has one polite actionable banner update', {concurrency: false}, async () => {
  const surface = await renderRuntime('starting');
  try {
    assert.equal(document.querySelectorAll('[role="status"][aria-live="polite"]').length, 1);
    assert.equal(document.querySelector('[role="alert"]'), null);
    assert.equal(document.querySelector('[data-runtime-status="warming"]')?.getAttribute('aria-atomic'), 'true');
    assert.match(document.body.textContent ?? '', /Runtime is warming up/);
    assert.ok([...document.querySelectorAll('button')].some((button) => button.textContent?.includes('Retry')));
  } finally {
    await surface.restore();
  }
});

test('runtime error has one actionable surface and copies the exact detail', {concurrency: false}, async () => {
  const surface = await renderRuntime('error', 'socket closed');
  try {
    let copied = '';
    Object.defineProperty(navigator, 'clipboard', {
      value: {writeText: async (text: string) => { copied = text; }},
      configurable: true,
    });
    assert.equal(document.querySelectorAll('[role="status"][aria-live="polite"]').length, 1);
    assert.equal(document.querySelector('[role="alert"]'), null);
    assert.equal((document.body.textContent ?? '').match(/socket closed/g)?.length, 1);
    assert.ok(document.querySelector('a[href="/settings"]'));
    const copyButton = [...document.querySelectorAll('button')].find((button) => button.textContent?.includes('Copy details'));
    assert.ok(copyButton);
    await act(async () => { copyButton.click(); });
    assert.equal(copied, 'socket closed');
    assert.match(copyButton.textContent ?? '', /Details copied/);
  } finally {
    await surface.restore();
  }
});

test('disconnected runtime uses the canonical banner without a header duplicate', {concurrency: false}, async () => {
  const surface = await renderRuntime('error', null, true);
  try {
    assert.equal(document.querySelectorAll('[role="status"][aria-live="polite"]').length, 1);
    assert.equal(document.querySelector('[data-runtime-status="disconnected"]')?.getAttribute('aria-atomic'), 'true');
    assert.match(document.body.textContent ?? '', /Runtime connection lost/);
    assert.doesNotMatch(document.body.textContent ?? '', /Runtime ready/);
    assert.ok(document.querySelector('a[href="/settings"]'));
  } finally {
    await surface.restore();
  }
});

test('runtime detail copy uses and removes a transient fallback selection', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>');
  let selected = '';
  Object.defineProperty(dom.window.document, 'execCommand', {
    value: () => {
      selected = dom.window.document.querySelector('textarea')?.value ?? '';
      return true;
    },
    configurable: true,
  });
  const copied = await copyRuntimeDetails(
    'runtime disconnected',
    {writeText: async () => { throw new Error('denied'); }},
    dom.window.document,
  );
  assert.equal(copied, true);
  assert.equal(selected, 'runtime disconnected');
  assert.equal(dom.window.document.querySelector('textarea'), null);
  dom.window.close();
});

test('runtime detail copy cleans up when every clipboard path is denied', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>');
  Object.defineProperty(dom.window.document, 'execCommand', {
    value: () => { throw new Error('blocked'); },
    configurable: true,
  });
  const copied = await copyRuntimeDetails(
    'runtime disconnected',
    {writeText: async () => { throw new Error('denied'); }},
    dom.window.document,
  );
  assert.equal(copied, false);
  assert.equal(dom.window.document.querySelector('textarea'), null);
  dom.window.close();
});

test('runtime status wording is available in every supported locale', () => {
  const locales: Locale[] = ['en', 'ja', 'zh', 'ko', 'es', 'fr', 'de', 'pt', 'ru', 'ar'];
  const keys = [
    'runtime.healthy_label',
    'runtime.warming_title',
    'runtime.disconnected_title',
    'runtime.error_title',
    'runtime.retry',
    'runtime.open_settings',
    'runtime.copy_details',
  ];
  for (const locale of locales) {
    for (const key of keys) assert.notEqual(translate(key, undefined, locale), key);
  }
});
