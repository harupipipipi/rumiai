import assert from 'node:assert/strict';
import {afterEach, beforeEach, test} from 'node:test';
import {act, type ReactNode} from 'react';
import type {Root} from 'react-dom/client';
import {JSDOM} from 'jsdom';

import type {Profile, Toast} from '@/src/store';
import {useAppStore} from '@/src/store';

interface Deferred<T> {
  promise: Promise<T>;
  reject: (reason?: unknown) => void;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let reject!: Deferred<T>['reject'];
  let resolve!: Deferred<T>['resolve'];
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return {promise, reject, resolve};
}

const originalProfile: Profile = {
  avatar: '/avatar.png',
  username: 'Rumi user',
  language: 'en',
  job: 'Engineer',
  connected: true,
};

const storeAddFlow = useAppStore.getState().addFlow;
const storeUpdateProfile = useAppStore.getState().updateProfile;
let createRoot: typeof import('react-dom/client')['createRoot'];
let container: HTMLDivElement | null = null;
let dom: JSDOM | null = null;
let feedback: Array<Pick<Toast, 'message' | 'type'>> = [];
let FlowsPage: typeof import('./Flows')['Flows'];
let root: Root | null = null;
let SettingsPage: typeof import('./Settings')['Settings'];

class ResizeObserverMock {
  disconnect(): void {}
  observe(): void {}
  unobserve(): void {}
}

async function settlePromises(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

async function renderPage(page: ReactNode): Promise<void> {
  assert.ok(root);
  await act(async () => {
    root?.render(page);
    await settlePromises();
  });
}

function buttonByText(text: string): HTMLButtonElement {
  const button = Array.from(container?.querySelectorAll('button') ?? [])
    .find((candidate) => candidate.textContent?.trim() === text);
  assert.ok(button, `Missing button: ${text}`);
  return button;
}

function click(element: HTMLElement): void {
  assert.ok(dom);
  element.dispatchEvent(new dom.window.MouseEvent('click', {
    bubbles: true,
    cancelable: true,
  }));
}

function changeInput(input: HTMLInputElement, value: string): void {
  assert.ok(dom);
  const valueSetter = Object.getOwnPropertyDescriptor(
    dom.window.HTMLInputElement.prototype,
    'value',
  )?.set;
  assert.ok(valueSetter);
  valueSetter.call(input, value);
  input.dispatchEvent(new dom.window.Event('input', {bubbles: true}));
}

function successfulResponse(data: unknown): Response {
  return new Response(JSON.stringify({success: true, data, error: null}), {
    headers: {'Content-Type': 'application/json'},
    status: 200,
  });
}

beforeEach(async () => {
  dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://127.0.0.1:8765/panel/',
  });
  const animationFrames = new Map<number, ReturnType<typeof setTimeout>>();
  let animationFrameId = 0;
  const requestAnimationFrame = (callback: FrameRequestCallback): number => {
    animationFrameId += 1;
    const id = animationFrameId;
    animationFrames.set(id, setTimeout(() => callback(Date.now()), 0));
    return id;
  };
  const cancelAnimationFrame = (id: number): void => {
    const timer = animationFrames.get(id);
    if (timer) clearTimeout(timer);
    animationFrames.delete(id);
  };
  const matchMedia = () => ({
    addEventListener: () => {},
    addListener: () => {},
    dispatchEvent: () => false,
    matches: false,
    media: '',
    onchange: null,
    removeEventListener: () => {},
    removeListener: () => {},
  });

  Object.defineProperties(globalThis, {
    IS_REACT_ACT_ENVIRONMENT: {configurable: true, value: true, writable: true},
    cancelAnimationFrame: {configurable: true, value: cancelAnimationFrame, writable: true},
    document: {configurable: true, value: dom.window.document, writable: true},
    Element: {configurable: true, value: dom.window.Element, writable: true},
    getComputedStyle: {configurable: true, value: dom.window.getComputedStyle, writable: true},
    HTMLElement: {configurable: true, value: dom.window.HTMLElement, writable: true},
    Image: {configurable: true, value: dom.window.Image, writable: true},
    localStorage: {configurable: true, value: dom.window.localStorage, writable: true},
    MouseEvent: {configurable: true, value: dom.window.MouseEvent, writable: true},
    MutationObserver: {configurable: true, value: dom.window.MutationObserver, writable: true},
    navigator: {configurable: true, value: dom.window.navigator, writable: true},
    Node: {configurable: true, value: dom.window.Node, writable: true},
    requestAnimationFrame: {configurable: true, value: requestAnimationFrame, writable: true},
    ResizeObserver: {configurable: true, value: ResizeObserverMock, writable: true},
    sessionStorage: {configurable: true, value: dom.window.sessionStorage, writable: true},
    SVGElement: {configurable: true, value: dom.window.SVGElement, writable: true},
    window: {configurable: true, value: dom.window, writable: true},
  });
  Object.defineProperties(dom.window, {
    cancelAnimationFrame: {configurable: true, value: cancelAnimationFrame},
    matchMedia: {configurable: true, value: matchMedia},
    requestAnimationFrame: {configurable: true, value: requestAnimationFrame},
    ResizeObserver: {configurable: true, value: ResizeObserverMock},
  });

  ({createRoot} = await import('react-dom/client'));
  ({Flows: FlowsPage} = await import('./Flows'));
  ({Settings: SettingsPage} = await import('./Settings'));

  feedback = [];
  container = dom.window.document.querySelector<HTMLDivElement>('#root');
  assert.ok(container);
  root = createRoot(container);
  useAppStore.setState({
    addFlow: storeAddFlow,
    addToast: (message, type) => feedback.push({message, type}),
    apiError: null,
    dialog: null,
    flows: [],
    isLoading: false,
    loadFlows: async () => {},
    loadProfile: async () => {},
    loadVersion: async () => {},
    profile: {...originalProfile},
    toasts: [],
    updateProfile: storeUpdateProfile,
  });
});

afterEach(async () => {
  if (root) {
    await act(async () => {
      root?.unmount();
    });
  }
  dom?.window.close();
  container = null;
  dom = null;
  root = null;
});

test('Flows keeps a rejected create draft and blocks rapid duplicate saves', async () => {
  const createRequest = deferred<Response>();
  let createCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (_input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      if (init?.method !== 'POST') {
        return Promise.reject(new Error(`Unexpected request: ${init?.method ?? 'GET'}`));
      }
      createCalls += 1;
      return createRequest.promise;
    },
    writable: true,
  });

  await renderPage(<FlowsPage />);
  await act(async () => {
    click(buttonByText('New Flow'));
    await settlePromises();
  });
  const nameInput = container?.querySelector<HTMLInputElement>(
    'input[placeholder^="Flow name"]',
  );
  assert.ok(nameInput);
  await act(async () => {
    changeInput(nameInput, 'recoverable-draft');
    await settlePromises();
  });

  await act(async () => {
    click(buttonByText('Save'));
    await settlePromises();
  });
  assert.equal(createCalls, 1);
  assert.equal(buttonByText('Save').disabled, true);
  assert.equal(buttonByText('Save').getAttribute('aria-busy'), 'true');

  await act(async () => {
    click(buttonByText('Save'));
    await settlePromises();
  });
  assert.equal(createCalls, 1);

  await act(async () => {
    createRequest.reject(new Error('create rejected'));
    await settlePromises();
  });

  const retainedInput = container?.querySelector<HTMLInputElement>(
    'input[placeholder^="Flow name"]',
  );
  assert.ok(retainedInput);
  assert.equal(retainedInput.value, 'recoverable-draft');
  assert.equal(buttonByText('Save').disabled, false);
  assert.equal(buttonByText('Save').getAttribute('aria-busy'), null);
  assert.deepEqual(useAppStore.getState().flows, []);
  assert.deepEqual(feedback, [{message: 'create rejected', type: 'error'}]);
});

test('Settings stays pending through refresh rejection and retains the edited profile', async () => {
  const updateRequest = deferred<Response>();
  const refreshRequest = deferred<Response>();
  const requests: string[] = [];
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      requests.push(`${method} ${String(input)}`);
      return method === 'PUT' ? updateRequest.promise : refreshRequest.promise;
    },
    writable: true,
  });

  await renderPage(<SettingsPage />);
  const usernameInput = Array.from(container?.querySelectorAll('input') ?? [])
    .find((input) => input.value === originalProfile.username);
  assert.ok(usernameInput);
  await act(async () => {
    changeInput(usernameInput, 'Edited user');
    await settlePromises();
  });

  await act(async () => {
    click(buttonByText('Save'));
    await settlePromises();
  });
  assert.deepEqual(requests, ['PUT /api/panel/settings/profile']);
  assert.equal(buttonByText('Save').disabled, true);
  assert.equal(buttonByText('Save').getAttribute('aria-busy'), 'true');

  await act(async () => {
    click(buttonByText('Save'));
    await settlePromises();
  });
  assert.deepEqual(requests, ['PUT /api/panel/settings/profile']);

  await act(async () => {
    updateRequest.resolve(successfulResponse({profile: {}}));
    await settlePromises();
  });
  assert.deepEqual(requests, [
    'PUT /api/panel/settings/profile',
    'GET /api/panel/settings/profile',
  ]);
  assert.equal(buttonByText('Save').disabled, true);

  await act(async () => {
    refreshRequest.reject(new Error('profile refresh rejected'));
    await settlePromises();
  });

  const retainedUsername = Array.from(container?.querySelectorAll('input') ?? [])
    .find((input) => input.value === 'Edited user');
  assert.ok(retainedUsername);
  assert.equal(buttonByText('Save').disabled, false);
  assert.equal(buttonByText('Save').getAttribute('aria-busy'), null);
  assert.equal(useAppStore.getState().profile.username, originalProfile.username);
  assert.deepEqual(feedback, [{message: 'profile refresh rejected', type: 'error'}]);
});
