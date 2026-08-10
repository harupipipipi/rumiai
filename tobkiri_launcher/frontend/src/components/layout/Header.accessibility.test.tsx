import assert from 'node:assert/strict';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import test from 'node:test';
import {MemoryRouter} from 'react-router';

import {Header} from './Header';
import {useAppStore} from '@/src/store';

function createSurface(): {dom: JSDOM; container: HTMLElement; root: Root} {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/panel/',
  });
  Object.defineProperties(globalThis, {
    window: {value: dom.window, configurable: true},
    document: {value: dom.window.document, configurable: true},
    navigator: {value: dom.window.navigator, configurable: true},
    localStorage: {value: dom.window.localStorage, configurable: true},
  });
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const container = dom.window.document.querySelector<HTMLElement>('#root');
  assert.ok(container);
  return {dom, container, root: createRoot(container)};
}

const nextTick = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

async function waitForFocus(dom: JSDOM, target: HTMLElement): Promise<void> {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    if (dom.window.document.activeElement === target) return;
    await act(async () => { await nextTick(); });
  }
  assert.ok(dom.window.document.activeElement === target, 'expected the popover to move focus');
}

let domTestLock = Promise.resolve();

async function acquireDomTestLock(): Promise<() => void> {
  const previous = domTestLock;
  let release!: () => void;
  domTestLock = new Promise<void>((resolve) => {
    release = resolve;
  });
  await previous;
  return release;
}

test('Header avatar is an actionable Profile/Settings entry with focus, Escape, return focus, and tap behavior', {concurrency: false}, async () => {
  const release = await acquireDomTestLock();
  const previousState = useAppStore.getState();
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const {dom, container, root} = createSurface();
  useAppStore.setState({profile: {...previousState.profile, username: 'Test User'}});
  try {
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={['/']}>
          <Header />
        </MemoryRouter>,
      );
    });
    const trigger = container.querySelector<HTMLButtonElement>('button[aria-label="Test User profile and settings"]');
    assert.ok(trigger);
    trigger.focus();
    assert.ok(dom.window.document.activeElement === trigger);

    await act(async () => { trigger.click(); await nextTick(); });
    const dialog = dom.window.document.querySelector('[role="dialog"][aria-label="Profile menu"]');
    assert.ok(dialog);
    assert.ok(dialog.querySelector('a[href="/profile"]'));
    assert.ok(dialog.querySelector('a[href="/settings"]'));
    assert.equal(dialog.querySelector('[role="menuitem"]'), null);

    await act(async () => {
      dom.window.dispatchEvent(new dom.window.KeyboardEvent('keydown', {key: 'Escape'}));
      await nextTick();
    });
    assert.equal(dom.window.document.querySelector('[role="dialog"][aria-label="Profile menu"]'), null);
    await act(async () => { await nextTick(); });
    assert.ok(dom.window.document.activeElement === trigger);

    await act(async () => { trigger.click(); await nextTick(); });
    const settings = dom.window.document.querySelector<HTMLAnchorElement>('[role="dialog"][aria-label="Profile menu"] a[href="/settings"]');
    assert.ok(settings);
    await act(async () => { settings.click(); await nextTick(); });
    assert.equal(dom.window.document.querySelector('[role="dialog"][aria-label="Profile menu"]'), null);
  } finally {
    await act(async () => { root.unmount(); });
    useAppStore.setState(previousState, true);
    dom.window.close();
    Object.defineProperty(globalThis, 'window', {value: previousWindow, configurable: true});
    Object.defineProperty(globalThis, 'document', {value: previousDocument, configurable: true});
    release();
  }
});

test('mobile navigation exposes a named menu, moves focus, and closes on Escape or selection', {concurrency: false}, async () => {
  const release = await acquireDomTestLock();
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const {dom, container, root} = createSurface();
  try {
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={['/']}>
          <Header />
        </MemoryRouter>,
      );
    });
    const trigger = container.querySelector<HTMLButtonElement>('button[aria-label="Open navigation"]');
    assert.ok(trigger);
    assert.equal(trigger.getAttribute('aria-haspopup'), 'menu');
    assert.equal(trigger.getAttribute('aria-expanded'), 'false');

    await act(async () => { trigger.click(); await nextTick(); });
    const menu = dom.window.document.querySelector<HTMLElement>('[role="menu"][aria-label="Mobile navigation"]');
    assert.ok(menu);
    assert.equal(trigger.getAttribute('aria-expanded'), 'true');
    assert.equal(trigger.getAttribute('aria-controls'), menu.id);
    const firstItem = menu.querySelector<HTMLElement>('[role="menuitem"]');
    assert.ok(firstItem);
    await waitForFocus(dom, firstItem);

    await act(async () => {
      dom.window.dispatchEvent(new dom.window.KeyboardEvent('keydown', {key: 'Escape'}));
      await nextTick();
    });
    assert.equal(dom.window.document.querySelector('[role="menu"][aria-label="Mobile navigation"]'), null);
    assert.ok(dom.window.document.activeElement === trigger);

    await act(async () => { trigger.click(); await nextTick(); });
    const packsLink = dom.window.document.querySelector<HTMLAnchorElement>('[role="menuitem"][href="/packs"]');
    assert.ok(packsLink);
    await act(async () => { packsLink.click(); await nextTick(); });
    assert.equal(dom.window.document.querySelector('[role="menu"][aria-label="Mobile navigation"]'), null);
  } finally {
    await act(async () => { root.unmount(); });
    dom.window.close();
    Object.defineProperty(globalThis, 'window', {value: previousWindow, configurable: true});
    Object.defineProperty(globalThis, 'document', {value: previousDocument, configurable: true});
    release();
  }
});
