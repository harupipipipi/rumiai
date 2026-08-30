import assert from 'node:assert/strict';
import {act, type ComponentProps} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import test from 'node:test';
import {MemoryRouter, Route, Routes} from 'react-router';
import {renderToStaticMarkup} from 'react-dom/server';

import {HomeRoute, SetupVerificationBanner, SetupVerificationGate} from './App';

function gateProps(overrides: Partial<ComponentProps<typeof SetupVerificationGate>> = {}) {
  return {
    isSetupDone: true,
    runtimeReady: false,
    runtimeStatus: 'panel_ready' as const,
    runtimeDisconnected: false,
    defaultsBootstrapRequired: false,
    ...overrides,
  };
}

function createDom(): {dom: JSDOM; container: HTMLElement; root: Root} {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/panel/packs',
  });
  Object.defineProperties(globalThis, {
    window: {value: dom.window, configurable: true},
    document: {value: dom.window.document, configurable: true},
    navigator: {value: dom.window.navigator, configurable: true},
  });
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const container = dom.window.document.querySelector<HTMLElement>('#root');
  assert.ok(container);
  return {dom, container, root: createRoot(container)};
}

test('verification gate hides runtime children while health is unresolved', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <SetupVerificationGate {...gateProps()} onRetry={() => undefined}>
        <p>unsafe runtime page</p>
      </SetupVerificationGate>
    </MemoryRouter>,
  );

  assert.match(html, /data-testid="setup-verification-gate"/);
  assert.match(html, /role="status"/);
  assert.match(html, /aria-busy="true"/);
  assert.match(html, /Verifying Tobkiri setup/);
  assert.match(html, /Retry verification/);
  assert.match(html, /Open Setup/);
  assert.doesNotMatch(html, /unsafe runtime page/);
});

test('verification gate exposes an accessible blocked state after runtime failure', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <SetupVerificationGate {...gateProps({runtimeStatus: 'error'})}>
        <p>unsafe runtime page</p>
      </SetupVerificationGate>
    </MemoryRouter>,
  );

  assert.match(html, /role="alert"/);
  assert.match(html, /Setup verification is unavailable/);
  assert.doesNotMatch(html, /unsafe runtime page/);
});

test('verification banner keeps the recovery link visible without exposing runtime children', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <SetupVerificationBanner {...gateProps({isSetupDone: false, runtimeStatus: 'starting'})} />
    </MemoryRouter>,
  );

  assert.match(html, /data-testid="setup-verification-banner"/);
  assert.match(html, /Complete setup to continue/);
  assert.match(html, /Open Setup/);
  assert.match(html, /href="\/setup"/);
});

test('empty bootstrap keeps Home recovery-gated even when generic runtime health is ready', () => {
  const banner = renderToStaticMarkup(
    <MemoryRouter>
      <SetupVerificationBanner
        {...gateProps({
          defaultsBootstrapRequired: true,
          runtimeReady: true,
          runtimeStatus: 'runtime_ready',
        })}
      />
    </MemoryRouter>,
  );
  const gate = renderToStaticMarkup(
    <MemoryRouter>
      <SetupVerificationGate
        {...gateProps({
          defaultsBootstrapRequired: true,
          runtimeReady: true,
          runtimeStatus: 'runtime_ready',
        })}
      >
        <p>unsafe runtime page</p>
      </SetupVerificationGate>
    </MemoryRouter>,
  );

  assert.match(banner, /Complete setup to continue/);
  assert.match(banner, /Open Setup/);
  assert.match(gate, /Complete setup to continue/);
  assert.doesNotMatch(gate, /unsafe runtime page/);
});

test('Home route keeps its child catalog mounted behind an inline verification banner', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route
          path="/"
          element={
            <HomeRoute
              verificationBanner={
                <SetupVerificationBanner {...gateProps({isSetupDone: false, runtimeStatus: 'starting'})} />
              }
            />
          }
        >
          <Route index element={<div data-testid="home-profile-catalog">Profile catalog and CRUD</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );

  assert.match(html, /data-testid="setup-verification-banner"/);
  assert.match(html, /data-testid="home-profile-catalog"/);
  assert.doesNotMatch(html, /data-testid="setup-verification-gate"/);
  assert.doesNotMatch(html, /min-h-screen items-center/);
});

test('embedded verification gate blocks runtime route content inside the Home layout', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <SetupVerificationGate {...gateProps({runtimeStatus: 'error'})} embedded>
        <p>unsafe runtime route</p>
      </SetupVerificationGate>
    </MemoryRouter>,
  );

  assert.match(html, /data-testid="runtime-route-verification-gate"/);
  assert.match(html, /Open Setup/);
  assert.doesNotMatch(html, /unsafe runtime route/);
  assert.doesNotMatch(html, /<main/);
});

test('verified health renders the selected route and retry action is interactive', async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const previousNavigator = globalThis.navigator;
  const {dom, container, root} = createDom();
  let retries = 0;

  try {
    await act(async () => {
      root.render(
        <MemoryRouter>
          <SetupVerificationGate
            {...gateProps()}
            onRetry={async () => { retries += 1; }}
          >
            <p data-testid="safe-runtime-page">verified runtime page</p>
          </SetupVerificationGate>
        </MemoryRouter>,
      );
    });
    assert.equal(container.querySelector('[data-testid="safe-runtime-page"]'), null);
    const retry = container.querySelector<HTMLButtonElement>('button');
    assert.ok(retry);
    assert.equal(retry.disabled, false);
    await act(async () => { retry.click(); });
    assert.equal(retries, 1);

    await act(async () => {
      root.render(
        <MemoryRouter>
          <SetupVerificationGate
            {...gateProps({runtimeReady: true, runtimeStatus: 'runtime_ready'})}
          >
            <p data-testid="safe-runtime-page">verified runtime page</p>
          </SetupVerificationGate>
        </MemoryRouter>,
      );
    });
    assert.match(container.textContent ?? '', /verified runtime page/);
    assert.equal(container.querySelector('[data-testid="setup-verification-gate"]'), null);
  } finally {
    act(() => root.unmount());
    dom.window.close();
    Object.defineProperties(globalThis, {
      window: {value: previousWindow, configurable: true},
      document: {value: previousDocument, configurable: true},
      navigator: {value: previousNavigator, configurable: true},
    });
  }
});
