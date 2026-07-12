import assert from 'node:assert/strict';
import test from 'node:test';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {JSDOM} from 'jsdom';

import {AVATAR_OPTIONS, useAppStore} from '@/src/store';
import {Settings} from './Settings';

interface MountedPage {
  container: HTMLElement;
  root: Root;
  cleanup: () => Promise<void>;
}

async function mountSettings(language = 'en'): Promise<MountedPage> {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/settings',
  });
  const previousState = useAppStore.getState();
  Object.defineProperties(globalThis, {
    window: {value: dom.window, configurable: true},
    document: {value: dom.window.document, configurable: true},
    navigator: {value: dom.window.navigator, configurable: true},
    localStorage: {value: dom.window.localStorage, configurable: true},
  });
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  useAppStore.setState({
    profile: {
      avatar: AVATAR_OPTIONS[0],
      username: 'Rumi User',
      language,
      job: 'Designer',
      connected: true,
    },
    loadProfile: async () => {},
    loadVersion: async () => {},
    loadUpdates: async () => {},
    loadUpdateSettings: async () => {},
  });
  const container = dom.window.document.querySelector<HTMLElement>('#root');
  assert.ok(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<Settings />);
  });
  return {
    container,
    root,
    cleanup: async () => {
      await act(async () => root.unmount());
      useAppStore.setState(previousState, true);
      dom.window.close();
    },
  };
}

test('Settings exposes field names and visual selector state in English and Japanese', async () => {
  for (const locale of ['en', 'ja']) {
    const page = await mountSettings(locale);
    try {
      const username = page.container.querySelector<HTMLInputElement>('#settings-username');
      const language = page.container.querySelector<HTMLSelectElement>('#settings-language');
      const job = page.container.querySelector<HTMLInputElement>('#settings-job');
      assert.ok(username?.labels?.[0]?.textContent?.trim());
      assert.ok(language?.labels?.[0]?.textContent?.trim());
      assert.ok(job?.labels?.[0]?.textContent?.trim());

      const changeAvatar = Array.from(page.container.querySelectorAll('button')).find(
        button => button.getAttribute('aria-controls') === 'settings-avatar-options',
      );
      assert.ok(changeAvatar);
      await act(async () => changeAvatar.click());
      const avatarButtons = Array.from(
        page.container.querySelectorAll<HTMLButtonElement>('#settings-avatar-options button'),
      );
      assert.equal(avatarButtons.length, AVATAR_OPTIONS.length);
      assert.equal(new Set(avatarButtons.map(button => button.getAttribute('aria-label'))).size, AVATAR_OPTIONS.length);
      assert.equal(avatarButtons.filter(button => button.getAttribute('aria-pressed') === 'true').length, 1);

      const colorGroup = page.container.querySelector('[aria-labelledby="settings-color-mode-label"]');
      const themeGroup = page.container.querySelector('[aria-labelledby="settings-style-theme-label"]');
      assert.equal(colorGroup?.querySelectorAll('button[aria-pressed]').length, 2);
      assert.equal(colorGroup?.querySelectorAll('button[aria-pressed="true"]').length, 1);
      assert.equal(themeGroup?.querySelectorAll('button[aria-pressed]').length, 4);
      assert.equal(themeGroup?.querySelectorAll('button[aria-pressed="true"]').length, 1);
    } finally {
      await page.cleanup();
    }
  }
});

test('Settings tabs implement roving focus, arrow keys, and linked tabpanels', async () => {
  const page = await mountSettings();
  try {
    const profileTab = page.container.querySelector<HTMLButtonElement>('#settings-profile-tab');
    const versionTab = page.container.querySelector<HTMLButtonElement>('#settings-version-tab');
    assert.ok(profileTab);
    assert.ok(versionTab);
    assert.equal(profileTab.getAttribute('aria-controls'), 'settings-profile-panel');
    assert.equal(profileTab.tabIndex, 0);
    assert.equal(versionTab.tabIndex, -1);
    assert.equal(page.container.querySelector('[role="tabpanel"]')?.getAttribute('aria-labelledby'), profileTab.id);

    profileTab.focus();
    await act(async () => {
      profileTab.dispatchEvent(new window.KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}));
    });
    assert.equal(document.activeElement, versionTab);
    assert.equal(versionTab.getAttribute('aria-selected'), 'true');
    assert.equal(versionTab.tabIndex, 0);
    assert.equal(profileTab.tabIndex, -1);
    assert.equal(page.container.querySelector('[role="tabpanel"]')?.id, 'settings-version-panel');

    await act(async () => {
      versionTab.dispatchEvent(new window.KeyboardEvent('keydown', {key: 'Home', bubbles: true}));
    });
    assert.equal(document.activeElement, profileTab);
    assert.equal(page.container.querySelector('[role="tabpanel"]')?.id, 'settings-profile-panel');
  } finally {
    await page.cleanup();
  }
});
