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
  invocations: string[];
  cleanup: () => Promise<void>;
}

async function mountSettings(language = 'en', desktopShell = false): Promise<MountedPage> {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/settings',
  });
  const invocations: string[] = [];
  if (desktopShell) {
    Object.defineProperty(dom.window, '__TAURI__', {
      configurable: true,
      value: {
        core: {
          invoke: async (command: string) => {
            invocations.push(command);
            if (command === 'debug_approval_status') {
              return {state: 'disabled', reason: 'not_armed'};
            }
            if (command === 'arm_debug_approval') {
              return {state: 'armed', armed_remaining_seconds: 300};
            }
            if (command === 'get_background_control_status') {
              return {enabled: true, app_visible: true, kernel_running: true, windows: []};
            }
            if (command === 'get_desktop_system_info') {
              return null;
            }
            return null;
          },
        },
      },
    });
    dom.window.confirm = () => {
      throw new Error('native confirmation must not be used');
    };
  }
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
    invocations,
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
      const themeButtons = Array.from(themeGroup?.querySelectorAll<HTMLButtonElement>('button[aria-pressed]') ?? []);
      assert.deepEqual(themeButtons.map(button => button.textContent?.trim()), ['Rounded', 'Minimal']);
      assert.equal(themeGroup?.querySelectorAll('button[aria-pressed="true"]').length, 1);
    } finally {
      await page.cleanup();
    }
  }
});

test('Developer Debug Approval delegates confirmation directly to the native command', async () => {
  const page = await mountSettings('en', true);
  try {
    const versionTab = page.container.querySelector<HTMLButtonElement>('#settings-version-tab');
    assert.ok(versionTab);
    await act(async () => {
      versionTab.click();
      await Promise.resolve();
    });

    const toggle = page.container.querySelector<HTMLButtonElement>(
      'button[aria-label="Developer Debug Approval"]',
    );
    const duration = page.container.querySelector<HTMLSelectElement>('#debug-approval-duration');
    assert.ok(toggle);
    assert.ok(duration);
    assert.deepEqual(
      Array.from(duration.options).map(option => option.value),
      ['1h', '1d', '1w', '1mo', 'permanent'],
    );
    await act(async () => {
      toggle.click();
      await Promise.resolve();
    });

    assert.equal(page.invocations.includes('arm_debug_approval'), true);
    assert.match(page.container.textContent ?? '', /ARMED/);
  } finally {
    await page.cleanup();
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
