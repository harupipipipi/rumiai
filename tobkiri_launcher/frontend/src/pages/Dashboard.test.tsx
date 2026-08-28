import assert from 'node:assert/strict';
import test from 'node:test';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import {MemoryRouter} from 'react-router';

import {
  copyTextToClipboard,
  nextDuplicateProfileId,
  Dashboard,
} from './Dashboard';
import type {NamedProfileRegistry} from '@/src/lib/api';
import {useAppStore} from '@/src/store';

const digest = (character: string): string => `sha256:${character.repeat(64)}`;

function profileRecord(profileId: string, displayName: string, revision: string) {
  return {
    profile_id: profileId,
    profile_revision: revision,
    profile: {profile_id: profileId, display_name: displayName},
    order: profileId === 'defaults' ? 0 : 1,
    parent_revision: null,
    tombstone: false,
    created_at: 1,
    updated_at: 1,
    legacy_ids: [],
  };
}

function profileRegistry(): NamedProfileRegistry {
  return {
    profile_registry_api_version: 'io.tobkiri.profile-registry.v4',
    generation: 1,
    active_profile_id: 'defaults',
    active_profile_revision: digest('e'),
    profiles: [
      profileRecord('defaults', 'Defaults Profile', digest('a')),
      profileRecord('research', 'Research Profile', digest('b')),
    ],
  };
}

function createDashboardDom(): {dom: JSDOM; container: HTMLElement; root: Root} {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/panel/',
  });
  Object.defineProperties(globalThis, {
    window: {value: dom.window, configurable: true},
    document: {value: dom.window.document, configurable: true},
    navigator: {value: dom.window.navigator, configurable: true},
    localStorage: {value: dom.window.localStorage, configurable: true},
    sessionStorage: {value: dom.window.sessionStorage, configurable: true},
  });
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const container = dom.window.document.querySelector<HTMLElement>('#root');
  assert.ok(container);
  return {dom, container, root: createRoot(container)};
}

function jsonResponse(data: unknown): Response {
  return new Response(JSON.stringify({success: true, data}), {
    headers: {'Content-Type': 'application/json'},
  });
}

function buttonByLabel(container: HTMLElement, label: string): HTMLButtonElement {
  const button = container.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`);
  assert.ok(button, `missing button ${label}`);
  return button;
}

function linkByLabel(container: HTMLElement, label: string): HTMLAnchorElement {
  const link = container.querySelector<HTMLAnchorElement>(`a[aria-label="${label}"]`);
  assert.ok(link, `missing link ${label}`);
  return link;
}

async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

test('copyTextToClipboard copies the complete runtime error message', async () => {
  let copied = '';
  const success = await copyTextToClipboard('Kernel failed to start', {
    writeText: async (text: string) => {
      copied = text;
    },
  });

  assert.equal(success, true);
  assert.equal(copied, 'Kernel failed to start');
});

test('copyTextToClipboard returns false when the clipboard is unavailable', async () => {
  const success = await copyTextToClipboard('message', undefined);
  assert.equal(success, false);
});

test('duplicate Profile IDs are deterministic and never privilege Defaults', () => {
  assert.equal(nextDuplicateProfileId('work-a', ['defaults', 'work-a']), 'work-a-copy');
  assert.equal(
    nextDuplicateProfileId('work-a', ['work-a-copy', 'work-a-copy-2']),
    'work-a-copy-3',
  );
});

test('Home keeps Profile catalog and CRUD visible in needs_setup and disconnected states', async () => {
  const previousState = useAppStore.getState();
  const previousFetch = globalThis.fetch;
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const previousNavigator = globalThis.navigator;
  const previousLocalStorage = (globalThis as typeof globalThis & {localStorage?: unknown}).localStorage;
  const previousSessionStorage = (globalThis as typeof globalThis & {sessionStorage?: unknown}).sessionStorage;

  try {
    globalThis.fetch = (async (input) => {
      const path = new URL(String(input), 'http://localhost').pathname;
      assert.equal(path, '/api/v4/profiles');
      return jsonResponse(profileRegistry());
    }) as typeof fetch;

    const scenarios = [
      {name: 'needs_setup', isSetupDone: false, runtimeDisconnected: false},
      {name: 'disconnected', isSetupDone: true, runtimeDisconnected: true},
    ] as const;

    for (const scenario of scenarios) {
      useAppStore.setState({
        isSetupDone: scenario.isSetupDone,
        runtimeReady: false,
        runtimeStatus: scenario.name === 'disconnected' ? 'error' : 'starting',
        runtimeError: scenario.name === 'disconnected' ? 'runtime disconnected' : null,
        runtimeDisconnected: scenario.runtimeDisconnected,
        lastRuntimeHealthyAt: null,
      });
      const {dom, container, root} = createDashboardDom();
      try {
        await act(async () => {
          root.render(<MemoryRouter><Dashboard /></MemoryRouter>);
        });
        await settle();

        assert.match(container.textContent ?? '', /Profiles/, scenario.name);
        assert.match(container.textContent ?? '', /Defaults Profile/, scenario.name);
        assert.match(container.textContent ?? '', /Research Profile/, scenario.name);
        assert.ok(container.querySelector('input[aria-label="Search Profiles"]'));

        const addProfile = [...container.querySelectorAll('button')].find(
          (button) => button.textContent?.includes('Add Profile'),
        );
        assert.ok(addProfile, `${scenario.name}: Add Profile should be visible`);
        await act(async () => { addProfile.click(); });
        assert.ok(container.querySelector('input[aria-label="New Profile ID"]'));

        for (const displayName of ['Defaults Profile', 'Research Profile']) {
          assert.ok(buttonByLabel(container, `Edit ${displayName}`));
          assert.ok(buttonByLabel(container, `Duplicate ${displayName}`));
          assert.ok(buttonByLabel(container, `Delete ${displayName}`));
        }
        assert.equal(buttonByLabel(container, 'Delete Defaults Profile').disabled, true);
        assert.equal(buttonByLabel(container, 'Delete Research Profile').disabled, false);

        const activate = linkByLabel(container, 'Activate Research Profile');
        assert.equal(activate.getAttribute('aria-disabled'), 'true', scenario.name);
        assert.equal(activate.getAttribute('tabindex'), '-1', scenario.name);
        assert.match(activate.textContent ?? '', /Setup required/);
        assert.equal(buttonByLabel(container, 'Launch Defaults Profile').disabled, true, scenario.name);
      } finally {
        await act(async () => root.unmount());
        dom.window.close();
      }
    }
  } finally {
    globalThis.fetch = previousFetch;
    Object.defineProperties(globalThis, {
      window: {value: previousWindow, configurable: true},
      document: {value: previousDocument, configurable: true},
      navigator: {value: previousNavigator, configurable: true},
      localStorage: {value: previousLocalStorage, configurable: true},
      sessionStorage: {value: previousSessionStorage, configurable: true},
    });
    useAppStore.setState(previousState, true);
  }
});
