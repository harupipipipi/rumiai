import assert from 'node:assert/strict';
import {afterEach, beforeEach, test} from 'node:test';
import {act, StrictMode, useEffect, useRef, useState, type ReactNode} from 'react';
import type {Root} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import type {Node} from '@xyflow/react';

import type {Flow, Profile, Toast} from '@/src/store';
import {useAppStore} from '@/src/store';
import {fetchFlowDetail} from '@/src/lib/api';
import {useFlowExecution} from '@/src/hooks/useFlowExecution';

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

const existingFlow: Flow = {
  id: 'existing-flow',
  name: 'existing-flow.flow.yaml',
  content: [
    'flow_id: existing-flow',
    'name: existing-flow.flow.yaml',
    'base_pack: defaultspack',
    'steps: []',
    '',
  ].join('\n'),
};

const storeAddFlow = useAppStore.getState().addFlow;
const storeDeleteFlow = useAppStore.getState().deleteFlow;
const storeLoadFlows = useAppStore.getState().loadFlows;
const storeLoadProfile = useAppStore.getState().loadProfile;
const storeUpdateFlow = useAppStore.getState().updateFlow;
const storeUpdateProfile = useAppStore.getState().updateProfile;
let createRoot: typeof import('react-dom/client')['createRoot'];
let container: HTMLDivElement | null = null;
let dom: JSDOM | null = null;
let feedback: Array<Pick<Toast, 'message' | 'type'>> = [];
let DialogContainerPage: typeof import('@/src/components/ui/DialogContainer')['DialogContainer'];
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

function buttonsByText(text: string): HTMLButtonElement[] {
  return Array.from(container?.querySelectorAll('button') ?? [])
    .filter((candidate) => candidate.textContent?.trim() === text);
}

async function openFlowLibrary(): Promise<void> {
  if (buttonsByText('New Flow').length > 0) return;
  const opener = container?.querySelector<HTMLButtonElement>(
    'button[title="Open flow list"]',
  );
  assert.ok(opener, 'Missing flow library opener');
  await act(async () => {
    click(opener);
    await settlePromises();
  });
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

function apiFlow(flow: Flow) {
  return {
    flow_id: flow.id,
    name: flow.name,
    pack_id: 'defaultspack',
    filename: flow.name,
  };
}

function apiFlowDetail(flow: Flow, content = flow.content) {
  return {
    ...apiFlow(flow),
    yaml_content: content,
  };
}

function flowList(flows: Flow[]) {
  return {
    count: flows.length,
    flows: flows.map(apiFlow),
  };
}

function apiProfile(profile: Profile) {
  return {
    icon: profile.avatar,
    language: profile.language,
    occupation: profile.job,
    username: profile.username,
  };
}

function ExecutionCancellationHarness() {
  const [nodes, setNodes] = useState<Node[]>([
    {id: 'trigger', type: 'trigger', position: {x: 0, y: 0}, data: {}},
    {id: 'end', type: 'end', position: {x: 100, y: 0}, data: {}},
  ]);
  const execution = useFlowExecution(nodes, [], setNodes);
  return (
    <>
      <button type="button" onClick={() => { void execution.execute(); }}>Harness Execute</button>
      <button type="button" onClick={execution.cancel}>Harness Cancel</button>
      <output data-testid="harness-execution-state">
        {execution.isExecuting ? 'executing' : 'idle'}
      </output>
    </>
  );
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
    HTMLInputElement: {configurable: true, value: dom.window.HTMLInputElement, writable: true},
    HTMLTextAreaElement: {configurable: true, value: dom.window.HTMLTextAreaElement, writable: true},
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
  ({DialogContainer: DialogContainerPage} = await import('@/src/components/ui/DialogContainer'));
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
    deleteFlow: storeDeleteFlow,
    flows: [],
    isLoading: false,
    loadFlows: storeLoadFlows,
    loadProfile: storeLoadProfile,
    loadVersion: async () => {},
    profile: {...originalProfile},
    toasts: [],
    updateFlow: storeUpdateFlow,
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

test('Settings uses a fresh profile confirmation and ignores its late mount read', async () => {
  const staleMountRead = deferred<Response>();
  const freshRead = deferred<Response>();
  const editedProfile = {...originalProfile, username: 'Edited user'};
  const requests: string[] = [];
  let getCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      requests.push(`${method} ${String(input)}`);
      if (method === 'PUT') {
        return Promise.resolve(successfulResponse({
          profile: apiProfile(editedProfile),
          updated: true,
        }));
      }
      getCalls += 1;
      return getCalls === 1 ? staleMountRead.promise : freshRead.promise;
    },
    writable: true,
  });

  await renderPage(<SettingsPage />);
  assert.deepEqual(requests, ['GET /api/panel/settings/profile']);
  const usernameInput = Array.from(container?.querySelectorAll('input') ?? [])
    .find((input) => input.value === originalProfile.username);
  assert.ok(usernameInput);
  await act(async () => {
    changeInput(usernameInput, editedProfile.username);
    click(buttonByText('Save'));
    await settlePromises();
  });

  assert.deepEqual(requests, [
    'GET /api/panel/settings/profile',
    'PUT /api/panel/settings/profile',
    'GET /api/panel/settings/profile',
  ]);
  assert.equal(buttonByText('Save').disabled, true);
  assert.equal(buttonByText('Save').getAttribute('aria-busy'), 'true');

  await act(async () => {
    freshRead.resolve(successfulResponse({profile: apiProfile(editedProfile)}));
    await settlePromises();
  });
  assert.equal(useAppStore.getState().profile.username, editedProfile.username);
  assert.ok(Array.from(container?.querySelectorAll('input') ?? [])
    .some((input) => input.value === editedProfile.username));
  assert.deepEqual(feedback, [{message: 'Settings saved', type: 'success'}]);

  await act(async () => {
    staleMountRead.resolve(successfulResponse({profile: apiProfile(originalProfile)}));
    await settlePromises();
  });
  assert.equal(useAppStore.getState().profile.username, editedProfile.username);
  assert.ok(Array.from(container?.querySelectorAll('input') ?? [])
    .some((input) => input.value === editedProfile.username));
  assert.deepEqual(feedback, [{message: 'Settings saved', type: 'success'}]);
});

test('Settings accepts the backend-canonical trimmed username as confirmed state', async () => {
  const staleMountRead = deferred<Response>();
  const freshRead = deferred<Response>();
  const canonicalProfile = {...originalProfile, username: 'Alice'};
  const requests: string[] = [];
  let getCalls = 0;
  let submittedUsername = '';
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      requests.push(`${method} ${String(input)}`);
      if (method === 'PUT') {
        submittedUsername = JSON.parse(String(init?.body)).username as string;
        return Promise.resolve(successfulResponse({
          profile: apiProfile(canonicalProfile),
          updated: true,
        }));
      }
      getCalls += 1;
      return getCalls === 1 ? staleMountRead.promise : freshRead.promise;
    },
    writable: true,
  });

  await renderPage(<SettingsPage />);
  const usernameInput = Array.from(container?.querySelectorAll('input') ?? [])
    .find((input) => input.value === originalProfile.username);
  assert.ok(usernameInput);
  await act(async () => {
    changeInput(usernameInput, ' Alice ');
    click(buttonByText('Save'));
    await settlePromises();
  });
  assert.equal(submittedUsername, canonicalProfile.username);
  assert.deepEqual(requests, [
    'GET /api/panel/settings/profile',
    'PUT /api/panel/settings/profile',
    'GET /api/panel/settings/profile',
  ]);

  await act(async () => {
    freshRead.resolve(successfulResponse({profile: apiProfile(canonicalProfile)}));
    await settlePromises();
  });
  assert.equal(useAppStore.getState().profile.username, canonicalProfile.username);
  assert.ok(Array.from(container?.querySelectorAll('input') ?? [])
    .some((input) => input.value === canonicalProfile.username));
  assert.deepEqual(feedback, [{message: 'Settings saved', type: 'success'}]);

  await act(async () => {
    staleMountRead.resolve(successfulResponse({profile: apiProfile(originalProfile)}));
    await settlePromises();
  });
  assert.equal(useAppStore.getState().profile.username, canonicalProfile.username);
  assert.ok(Array.from(container?.querySelectorAll('input') ?? [])
    .some((input) => input.value === canonicalProfile.username));
  assert.deepEqual(feedback, [{message: 'Settings saved', type: 'success'}]);
});

test('Settings rejects an empty canonical username without a false save', async () => {
  const staleMountRead = deferred<Response>();
  const requests: string[] = [];
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      requests.push(`${init?.method ?? 'GET'} ${String(input)}`);
      return staleMountRead.promise;
    },
    writable: true,
  });

  await renderPage(<SettingsPage />);
  const usernameInput = Array.from(container?.querySelectorAll('input') ?? [])
    .find((input) => input.value === originalProfile.username);
  assert.ok(usernameInput);
  await act(async () => {
    changeInput(usernameInput, '   ');
    click(buttonByText('Save'));
    await settlePromises();
  });

  assert.deepEqual(requests, ['GET /api/panel/settings/profile']);
  assert.ok(Array.from(container?.querySelectorAll('input') ?? [])
    .some((input) => input.value === '   '));
  assert.deepEqual(feedback, [{
    message: 'username is required and must be a non-empty string',
    type: 'error',
  }]);

  await act(async () => {
    staleMountRead.resolve(successfulResponse({profile: apiProfile(originalProfile)}));
    await settlePromises();
  });
  assert.ok(Array.from(container?.querySelectorAll('input') ?? [])
    .some((input) => input.value === '   '));
  assert.deepEqual(feedback, [{
    message: 'username is required and must be a non-empty string',
    type: 'error',
  }]);
});

test('Settings keeps edited data when fresh profile state does not confirm the update', async () => {
  const staleMountRead = deferred<Response>();
  const freshRead = deferred<Response>();
  const requests: string[] = [];
  let getCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      requests.push(`${method} ${String(input)}`);
      if (method === 'PUT') {
        return Promise.resolve(successfulResponse({profile: apiProfile(originalProfile)}));
      }
      getCalls += 1;
      return getCalls === 1 ? staleMountRead.promise : freshRead.promise;
    },
    writable: true,
  });

  await renderPage(<SettingsPage />);
  const usernameInput = Array.from(container?.querySelectorAll('input') ?? [])
    .find((input) => input.value === originalProfile.username);
  assert.ok(usernameInput);
  await act(async () => {
    changeInput(usernameInput, 'Recoverable edit');
    click(buttonByText('Save'));
    await settlePromises();
  });
  assert.equal(buttonByText('Save').disabled, true);
  assert.deepEqual(requests, [
    'GET /api/panel/settings/profile',
    'PUT /api/panel/settings/profile',
    'GET /api/panel/settings/profile',
  ]);

  await act(async () => {
    freshRead.resolve(successfulResponse({profile: apiProfile(originalProfile)}));
    await settlePromises();
  });
  assert.ok(Array.from(container?.querySelectorAll('input') ?? [])
    .some((input) => input.value === 'Recoverable edit'));
  assert.equal(buttonByText('Save').disabled, false);
  assert.equal(useAppStore.getState().profile.username, originalProfile.username);
  assert.deepEqual(feedback, [{message: 'Profile update was not confirmed', type: 'error'}]);

  await act(async () => {
    staleMountRead.resolve(successfulResponse({profile: apiProfile(originalProfile)}));
    await settlePromises();
  });
  assert.ok(Array.from(container?.querySelectorAll('input') ?? [])
    .some((input) => input.value === 'Recoverable edit'));
  assert.deepEqual(feedback, [{message: 'Profile update was not confirmed', type: 'error'}]);
});

test('Flows create uses a fresh list and ignores the late mount list', async () => {
  const staleMountRead = deferred<Response>();
  const createdFlow: Flow = {
    id: 'confirmed-draft',
    name: 'confirmed-draft.flow.yaml',
    content: '',
  };
  const requests: string[] = [];
  let createdContent = '';
  let listCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      requests.push(`${method} ${path}`);
      if (method === 'POST') {
        createdContent = JSON.parse(String(init?.body)).yaml_content as string;
        return Promise.resolve(successfulResponse({
          created: true,
          filename: createdFlow.name,
          flow_id: createdFlow.id,
        }));
      }
      if (path === '/api/panel/flows') {
        listCalls += 1;
        return listCalls === 1
          ? staleMountRead.promise
          : Promise.resolve(successfulResponse(flowList([existingFlow, createdFlow])));
      }
      if (path.endsWith(`/${createdFlow.id}`)) {
        return Promise.resolve(successfulResponse(apiFlowDetail(createdFlow, createdContent)));
      }
      return Promise.resolve(successfulResponse(apiFlowDetail(existingFlow)));
    },
    writable: true,
  });
  useAppStore.setState({flows: [{...existingFlow}]});

  await renderPage(<FlowsPage />);
  await openFlowLibrary();
  await act(async () => {
    click(buttonByText('New Flow'));
    await settlePromises();
  });
  const nameInput = container?.querySelector<HTMLInputElement>(
    'input[placeholder^="Flow name"]',
  );
  assert.ok(nameInput);
  await act(async () => {
    changeInput(nameInput, 'confirmed-draft');
    await settlePromises();
  });
  await act(async () => {
    click(buttonByText('Save'));
    await settlePromises();
  });

  assert.deepEqual(requests.slice(0, 5), [
    'GET /api/panel/flows',
    `GET /api/panel/flows/${existingFlow.id}`,
    'POST /api/panel/flows',
    'GET /api/panel/flows',
    `GET /api/panel/flows/${createdFlow.id}`,
  ]);
  assert.equal(useAppStore.getState().flows.some((flow) => flow.id === createdFlow.id), true);
  assert.equal(container?.querySelector('input[placeholder^="Flow name"]'), null);
  assert.deepEqual(feedback, [{message: 'Flow created', type: 'success'}]);

  await act(async () => {
    staleMountRead.resolve(successfulResponse(flowList([existingFlow])));
    await settlePromises();
  });
  assert.equal(useAppStore.getState().flows.some((flow) => flow.id === createdFlow.id), true);
  assert.deepEqual(feedback, [{message: 'Flow created', type: 'success'}]);
});

test('Flows create retains its draft when the fresh list lacks the created flow', async () => {
  const staleMountRead = deferred<Response>();
  let listCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      if (method === 'POST') {
        return Promise.resolve(successfulResponse({
          created: true,
          filename: 'unconfirmed.flow.yaml',
          flow_id: 'unconfirmed',
        }));
      }
      if (path === '/api/panel/flows') {
        listCalls += 1;
        return listCalls === 1
          ? staleMountRead.promise
          : Promise.resolve(successfulResponse(flowList([existingFlow])));
      }
      return Promise.resolve(successfulResponse(apiFlowDetail(existingFlow)));
    },
    writable: true,
  });
  useAppStore.setState({flows: [{...existingFlow}]});

  await renderPage(<FlowsPage />);
  await openFlowLibrary();
  await act(async () => {
    click(buttonByText('New Flow'));
    await settlePromises();
  });
  const nameInput = container?.querySelector<HTMLInputElement>(
    'input[placeholder^="Flow name"]',
  );
  assert.ok(nameInput);
  await act(async () => {
    changeInput(nameInput, 'unconfirmed');
    await settlePromises();
  });
  await act(async () => {
    click(buttonByText('Save'));
    await settlePromises();
  });

  const retainedInput = container?.querySelector<HTMLInputElement>(
    'input[placeholder^="Flow name"]',
  );
  assert.ok(retainedInput);
  assert.equal(retainedInput.value, 'unconfirmed');
  assert.equal(useAppStore.getState().flows.some((flow) => flow.id === 'unconfirmed'), false);
  assert.deepEqual(feedback, [{message: 'Flow creation was not confirmed', type: 'error'}]);

  await act(async () => {
    staleMountRead.resolve(successfulResponse(flowList([existingFlow])));
    await settlePromises();
  });
  assert.equal(retainedInput.value, 'unconfirmed');
  assert.deepEqual(feedback, [{message: 'Flow creation was not confirmed', type: 'error'}]);
});

test('Flows update confirms fresh list and detail before success', async () => {
  const staleMountRead = deferred<Response>();
  const requests: string[] = [];
  let detailCalls = 0;
  let listCalls = 0;
  let updatedContent = '';
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      requests.push(`${method} ${path}`);
      if (method === 'PUT') {
        updatedContent = JSON.parse(String(init?.body)).yaml_content as string;
        return Promise.resolve(successfulResponse({
          filename: existingFlow.name,
          flow_id: existingFlow.id,
          updated: true,
        }));
      }
      if (path === '/api/panel/flows') {
        listCalls += 1;
        return listCalls === 1
          ? staleMountRead.promise
          : Promise.resolve(successfulResponse(flowList([existingFlow])));
      }
      detailCalls += 1;
      return Promise.resolve(successfulResponse(apiFlowDetail(
        existingFlow,
        detailCalls === 1 ? existingFlow.content : updatedContent,
      )));
    },
    writable: true,
  });
  useAppStore.setState({flows: [{...existingFlow}]});

  await renderPage(<FlowsPage />);
  await act(async () => {
    click(buttonByText('Save'));
    await settlePromises();
  });

  assert.deepEqual(requests, [
    'GET /api/panel/flows',
    `GET /api/panel/flows/${existingFlow.id}`,
    `PUT /api/panel/flows/${existingFlow.id}`,
    'GET /api/panel/flows',
    `GET /api/panel/flows/${existingFlow.id}`,
  ]);
  assert.deepEqual(feedback, [{message: 'Flow saved', type: 'success'}]);

  await act(async () => {
    staleMountRead.resolve(successfulResponse(flowList([
      {...existingFlow, id: 'stale-flow', name: 'stale-flow.flow.yaml'},
    ])));
    await settlePromises();
  });
  assert.deepEqual(useAppStore.getState().flows.map((flow) => flow.id), [existingFlow.id]);
  assert.deepEqual(feedback, [{message: 'Flow saved', type: 'success'}]);
});

test('Flows delete confirms fresh absence and ignores the late mount list', async () => {
  const staleMountRead = deferred<Response>();
  const requests: string[] = [];
  let listCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      requests.push(`${method} ${path}`);
      if (method === 'DELETE') {
        return Promise.resolve(successfulResponse({deleted: true, flow_id: existingFlow.id}));
      }
      if (path === '/api/panel/flows') {
        listCalls += 1;
        return listCalls === 1
          ? staleMountRead.promise
          : Promise.resolve(successfulResponse(flowList([])));
      }
      return Promise.resolve(successfulResponse(apiFlowDetail(existingFlow)));
    },
    writable: true,
  });
  useAppStore.setState({flows: [{...existingFlow}]});

  await renderPage(
    <>
      <FlowsPage />
      <DialogContainerPage />
    </>,
  );
  await act(async () => {
    click(buttonByText('Delete'));
    await settlePromises();
  });
  const deleteButtons = buttonsByText('Delete');
  assert.equal(deleteButtons.length, 2);
  await act(async () => {
    click(deleteButtons[1]);
    await settlePromises();
  });

  assert.deepEqual(requests, [
    'GET /api/panel/flows',
    `GET /api/panel/flows/${existingFlow.id}`,
    `DELETE /api/panel/flows/${existingFlow.id}`,
    'GET /api/panel/flows',
  ]);
  assert.deepEqual(useAppStore.getState().flows, []);
  assert.deepEqual(feedback, [{message: 'Flow deleted', type: 'success'}]);

  await act(async () => {
    staleMountRead.resolve(successfulResponse(flowList([existingFlow])));
    await settlePromises();
  });
  assert.deepEqual(useAppStore.getState().flows, []);
  assert.deepEqual(feedback, [{message: 'Flow deleted', type: 'success'}]);
});

test('Flows ignores an aborted initial detail after a failed update on the new selection', async () => {
  const staleInitialDetail = deferred<Response>();
  const secondFlow: Flow = {
    id: 'second-flow',
    name: 'second-flow.flow.yaml',
    content: [
      'flow_id: second-flow',
      'name: second-flow.flow.yaml',
      'base_pack: defaultspack',
      'steps: []',
      '',
    ].join('\n'),
  };
  let initialSignal: AbortSignal | null | undefined;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      if (method === 'PUT') return Promise.reject(new Error('update rejected'));
      if (path === '/api/panel/flows') {
        return Promise.resolve(successfulResponse(flowList([existingFlow, secondFlow])));
      }
      if (path.endsWith(`/${existingFlow.id}`)) {
        initialSignal = init?.signal;
        return staleInitialDetail.promise;
      }
      return Promise.resolve(successfulResponse(apiFlowDetail(secondFlow)));
    },
    writable: true,
  });
  useAppStore.setState({flows: [{...existingFlow}, {...secondFlow}]});

  await renderPage(<FlowsPage />);
  await openFlowLibrary();
  await act(async () => {
    click(buttonByText(secondFlow.name));
    await settlePromises();
  });
  assert.equal(initialSignal?.aborted, true);
  assert.equal(container?.querySelector('h2')?.textContent, secondFlow.name);

  await act(async () => {
    click(buttonByText('Save'));
    await settlePromises();
  });
  assert.deepEqual(feedback, [{message: 'update rejected', type: 'error'}]);

  await act(async () => {
    staleInitialDetail.reject(new Error('late detail rejected'));
    await settlePromises();
  });
  assert.equal(container?.querySelector('h2')?.textContent, secondFlow.name);
  assert.match(container?.textContent ?? '', /flow_id:\s*second-flow/);
  assert.deepEqual(feedback, [{message: 'update rejected', type: 'error'}]);
});

test('Flows ignores an aborted initial detail after a confirmed update on the new selection', async () => {
  const staleInitialDetail = deferred<Response>();
  const secondFlow: Flow = {
    id: 'confirmed-second-flow',
    name: 'confirmed-second-flow.flow.yaml',
    content: [
      'flow_id: confirmed-second-flow',
      'name: confirmed-second-flow.flow.yaml',
      'base_pack: defaultspack',
      'steps: []',
      '',
    ].join('\n'),
  };
  let detailCalls = 0;
  let initialSignal: AbortSignal | null | undefined;
  let updatedContent = '';
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      if (method === 'PUT') {
        updatedContent = JSON.parse(String(init?.body)).yaml_content as string;
        return Promise.resolve(successfulResponse({
          filename: secondFlow.name,
          flow_id: secondFlow.id,
          updated: true,
        }));
      }
      if (path === '/api/panel/flows') {
        return Promise.resolve(successfulResponse(flowList([existingFlow, secondFlow])));
      }
      if (path.endsWith(`/${existingFlow.id}`)) {
        initialSignal = init?.signal;
        return staleInitialDetail.promise;
      }
      detailCalls += 1;
      return Promise.resolve(successfulResponse(apiFlowDetail(
        secondFlow,
        detailCalls === 1 ? secondFlow.content : updatedContent,
      )));
    },
    writable: true,
  });
  useAppStore.setState({flows: [{...existingFlow}, {...secondFlow}]});

  await renderPage(<FlowsPage />);
  await openFlowLibrary();
  await act(async () => {
    click(buttonByText(secondFlow.name));
    await settlePromises();
  });
  assert.equal(initialSignal?.aborted, true);

  await act(async () => {
    click(buttonByText('Save'));
    await settlePromises();
  });
  assert.deepEqual(feedback, [{message: 'Flow saved', type: 'success'}]);

  await act(async () => {
    staleInitialDetail.resolve(successfulResponse(apiFlowDetail(existingFlow)));
    await settlePromises();
  });
  assert.equal(container?.querySelector('h2')?.textContent, secondFlow.name);
  assert.match(container?.textContent ?? '', /flow_id:\s*confirmed-second-flow/);
  assert.deepEqual(feedback, [{message: 'Flow saved', type: 'success'}]);
});

test('Flow detail StrictMode refetches the same ID after abort without obsolete feedback', async () => {
  let detailRequests = 0;
  let firstDetailSignal: AbortSignal | null | undefined;
  const obsoleteFeedback: string[] = [];
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      assert.equal(String(input), `/api/panel/flows/${existingFlow.id}`);
      detailRequests += 1;
      if (detailRequests === 1) {
        firstDetailSignal = init?.signal;
        return new Promise<Response>((_resolve, reject) => {
          const rejectAbort = () => reject(new DOMException('aborted', 'AbortError'));
          if (init?.signal?.aborted) {
            rejectAbort();
            return;
          }
          init?.signal?.addEventListener('abort', rejectAbort, {once: true});
        });
      }
      return Promise.resolve(successfulResponse(apiFlowDetail(existingFlow)));
    },
    writable: true,
  });

  function StrictDetailProbe() {
    const requestIdRef = useRef(0);
    const [status, setStatus] = useState('pending');

    useEffect(() => {
      const requestId = requestIdRef.current + 1;
      requestIdRef.current = requestId;
      const controller = new AbortController();
      let cancelled = false;
      void fetchFlowDetail(existingFlow.id, {signal: controller.signal})
        .then(() => {
          if (!cancelled && requestIdRef.current === requestId) setStatus('loaded');
        })
        .catch((error: unknown) => {
          if (cancelled || requestIdRef.current !== requestId) return;
          obsoleteFeedback.push(error instanceof Error ? error.message : String(error));
          setStatus('error');
        });
      return () => {
        cancelled = true;
        requestIdRef.current += 1;
        controller.abort();
      };
    }, []);

    return <div data-testid="strict-detail-status">{status}</div>;
  }

  await renderPage(
    <StrictMode>
      <StrictDetailProbe />
    </StrictMode>,
  );
  await act(async () => {
    await settlePromises();
  });

  assert.equal(detailRequests, 2);
  assert.equal(firstDetailSignal?.aborted, true);
  assert.equal(
    container?.querySelector('[data-testid="strict-detail-status"]')?.textContent,
    'loaded',
  );
  assert.deepEqual(obsoleteFeedback, []);
});

test('Flows blocks mutations and canvas interaction while initial detail is loading', async () => {
  const initialDetail = deferred<Response>();
  const requests: string[] = [];
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      requests.push(`${method} ${path}`);
      if (path === '/api/panel/flows') {
        return Promise.resolve(successfulResponse(flowList([existingFlow])));
      }
      return initialDetail.promise;
    },
    writable: true,
  });
  useAppStore.setState({flows: [{...existingFlow}]});

  await renderPage(<FlowsPage />);
  assert.equal(buttonByText('Save').disabled, true);
  assert.equal(buttonByText('Delete').disabled, true);
  assert.equal(buttonByText('Execute').disabled, true);
  assert.ok(container?.querySelector('.pointer-events-auto'));
  assert.deepEqual(requests, [
    'GET /api/panel/flows',
    `GET /api/panel/flows/${existingFlow.id}`,
  ]);

  await act(async () => {
    click(buttonByText('Save'));
    click(buttonByText('Delete'));
    click(buttonByText('Execute'));
    await settlePromises();
  });
  assert.equal(requests.some((request) => request.startsWith('PUT ')), false);
  assert.equal(requests.some((request) => request.startsWith('DELETE ')), false);
  assert.deepEqual(feedback, []);

  await act(async () => {
    initialDetail.resolve(successfulResponse(apiFlowDetail(existingFlow)));
    await settlePromises();
  });
  assert.equal(buttonByText('Save').disabled, false);
  assert.equal(buttonByText('Delete').disabled, false);
  assert.equal(buttonByText('Execute').disabled, false);
});

test('Flows locks every editing surface while an update is pending and restores it after confirmation', async () => {
  const updateResponse = deferred<Response>();
  const requests: string[] = [];
  let submittedContent = existingFlow.content;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      requests.push(`${method} ${path}`);
      if (method === 'PUT') {
        submittedContent = JSON.parse(String(init?.body)).yaml_content as string;
        return updateResponse.promise;
      }
      if (path === '/api/panel/flows') {
        return Promise.resolve(successfulResponse(flowList([existingFlow])));
      }
      return Promise.resolve(successfulResponse(apiFlowDetail(
        existingFlow,
        submittedContent,
      )));
    },
    writable: true,
  });
  useAppStore.setState({flows: [{...existingFlow}]});

  await renderPage(<FlowsPage />);
  assert.equal(container?.querySelector('[data-testid="flow-canvas"]')?.getAttribute('aria-busy'), 'false');

  await act(async () => {
    click(buttonByText('Save'));
    await settlePromises();
  });

  const canvas = container?.querySelector<HTMLElement>('[data-testid="flow-canvas"]');
  const toolbar = container?.querySelector<HTMLElement>('[data-testid="flow-editor-toolbar"]');
  assert.ok(canvas);
  assert.ok(toolbar);
  assert.equal(canvas.getAttribute('aria-busy'), 'true');
  assert.equal(canvas.hasAttribute('inert'), true);
  assert.equal(toolbar.getAttribute('aria-disabled'), 'true');
  assert.equal(toolbar.hasAttribute('inert'), true);
  assert.ok(canvas.querySelector('.pointer-events-auto'));
  assert.equal(buttonByText('Save').disabled, true);
  assert.equal(buttonByText('Delete').disabled, true);
  assert.equal(buttonByText('Execute').disabled, true);
  assert.equal(toolbar.querySelector<HTMLButtonElement>('button')?.disabled, true);
  assert.ok(Array.from(toolbar.querySelectorAll<HTMLElement>('[draggable]'))
    .every((step) => step.getAttribute('draggable') === 'false'));

  await act(async () => {
    assert.ok(dom);
    dom.window.dispatchEvent(new dom.window.KeyboardEvent('keydown', {
      bubbles: true,
      key: 'F7',
    }));
    await settlePromises();
  });
  assert.equal(requests.filter((request) => request.startsWith('PUT ')).length, 1);

  await act(async () => {
    updateResponse.resolve(successfulResponse({
      filename: existingFlow.name,
      flow_id: existingFlow.id,
      updated: true,
    }));
    await settlePromises();
  });

  assert.equal(canvas.getAttribute('aria-busy'), 'false');
  assert.equal(canvas.hasAttribute('inert'), false);
  assert.equal(toolbar.getAttribute('aria-disabled'), 'false');
  assert.equal(toolbar.hasAttribute('inert'), false);
  assert.equal(buttonByText('Save').disabled, false);
  assert.equal(buttonByText('Delete').disabled, false);
  assert.equal(buttonByText('Execute').disabled, false);
  assert.deepEqual(feedback, [{message: 'Flow saved', type: 'success'}]);
});

test('Flows blocks save and delete while execution is pending and restores them afterward', async () => {
  const requests: string[] = [];
  const secondFlow: Flow = {
    id: 'same-tick-selection',
    name: 'same-tick-selection.flow.yaml',
    content: 'flow_id: same-tick-selection\nsteps: []\n',
  };
  let submittedContent = existingFlow.content;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      requests.push(`${method} ${path}`);
      if (method === 'PUT') {
        submittedContent = JSON.parse(String(init?.body)).yaml_content as string;
        return Promise.resolve(successfulResponse({
          filename: existingFlow.name,
          flow_id: existingFlow.id,
          updated: true,
        }));
      }
      if (method === 'DELETE') {
        return Promise.resolve(successfulResponse({
          deleted: true,
          flow_id: existingFlow.id,
        }));
      }
      if (path === '/api/panel/flows') {
        return Promise.resolve(successfulResponse(flowList([existingFlow, secondFlow])));
      }
      const requestedFlow = path.endsWith(`/${secondFlow.id}`) ? secondFlow : existingFlow;
      return Promise.resolve(successfulResponse(apiFlowDetail(
        requestedFlow,
        requestedFlow.id === existingFlow.id ? submittedContent : requestedFlow.content,
      )));
    },
    writable: true,
  });
  useAppStore.setState({flows: [{...existingFlow}, {...secondFlow}]});

  await renderPage(
    <>
      <FlowsPage />
      <DialogContainerPage />
    </>,
  );

  await openFlowLibrary();
  const executeButton = buttonByText('Execute');
  const saveButton = buttonByText('Save');
  const deleteButton = buttonByText('Delete');
  const newFlowButton = buttonByText('New Flow');
  const secondFlowButton = buttonByText(secondFlow.name);
  const flowPane = container?.querySelector<HTMLElement>('.react-flow__pane');
  assert.ok(flowPane);

  await act(async () => {
    // All of these events are dispatched before React can commit isExecuting.
    // The synchronous guard must reject every action after the first Execute.
    click(executeButton);
    click(saveButton);
    click(deleteButton);
    click(newFlowButton);
    click(secondFlowButton);
    click(executeButton);
    assert.ok(dom);
    dom.window.dispatchEvent(new dom.window.KeyboardEvent('keydown', {
      bubbles: true,
      key: 'F7',
    }));
    dom.window.dispatchEvent(new dom.window.KeyboardEvent('keydown', {
      bubbles: true,
      ctrlKey: true,
      key: 'f',
    }));
    flowPane.dispatchEvent(new dom.window.MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: 40,
      clientY: 40,
    }));
    await settlePromises();
  });

  assert.equal(buttonByText('Save').disabled, true);
  assert.equal(buttonByText('Delete').disabled, true);
  assert.equal(buttonByText('New Flow').disabled, true);
  assert.equal(buttonByText(secondFlow.name).disabled, true);
  assert.equal(container?.querySelector('h2')?.textContent, existingFlow.name);
  assert.equal(
    container?.querySelector('input[placeholder="Search nodes..."]'),
    null,
  );
  assert.equal(useAppStore.getState().dialog, null);
  assert.equal(requests.some((request) => request.startsWith('PUT ')), false);
  assert.equal(requests.some((request) => request.startsWith('DELETE ')), false);

  await act(async () => {
    click(buttonByText('Save'));
    click(buttonByText('Delete'));
    await settlePromises();
  });

  assert.equal(requests.some((request) => request.startsWith('PUT ')), false);
  assert.equal(requests.some((request) => request.startsWith('DELETE ')), false);
  assert.equal(useAppStore.getState().dialog, null);

  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 900));
    await settlePromises();
  });

  assert.equal(buttonByText('Save').disabled, false);
  assert.equal(buttonByText('Delete').disabled, false);
  assert.equal(buttonByText('Execute').disabled, false);

  await act(async () => {
    click(buttonByText('Save'));
    await settlePromises();
  });
  assert.equal(requests.filter((request) => request.startsWith('PUT ')).length, 1);

  await act(async () => {
    click(buttonByText('Delete'));
    await settlePromises();
  });
  assert.notEqual(useAppStore.getState().dialog, null);
  assert.equal(requests.some((request) => request.startsWith('DELETE ')), false);
  assert.deepEqual(feedback, [
    {message: 'Flow execution complete', type: 'success'},
    {message: 'Flow saved', type: 'success'},
  ]);
});

test('Flows restores every interaction after an execution error result', async () => {
  const failingFlow: Flow = {
    id: 'failing-execution',
    name: 'failing-execution.flow.yaml',
    content: [
      'flow_id: failing-execution',
      'steps:',
      '  - id: emit',
      '    type: action',
      '',
    ].join('\n'),
  };
  const requests: string[] = [];
  const originalRandom = Math.random;
  Math.random = () => 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      requests.push(`${method} ${path}`);
      if (method === 'PUT') {
        return Promise.resolve(successfulResponse({
          filename: failingFlow.name,
          flow_id: failingFlow.id,
          updated: true,
        }));
      }
      if (path === '/api/panel/flows') {
        return Promise.resolve(successfulResponse(flowList([failingFlow])));
      }
      return Promise.resolve(successfulResponse(apiFlowDetail(failingFlow)));
    },
    writable: true,
  });
  useAppStore.setState({flows: [{...failingFlow}]});

  try {
    await renderPage(<FlowsPage />);
    await act(async () => {
      click(buttonByText('Execute'));
      await settlePromises();
    });
    assert.equal(buttonByText('Save').disabled, true);

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1400));
      await settlePromises();
    });

    assert.equal(buttonByText('Save').disabled, false);
    assert.equal(buttonByText('Delete').disabled, false);
    assert.equal(buttonByText('Execute').disabled, false);
    assert.deepEqual(feedback, [
      {message: 'Flow execution complete', type: 'error'},
    ]);

    await act(async () => {
      click(buttonByText('Save'));
      await settlePromises();
    });
    assert.equal(requests.filter((request) => request.startsWith('PUT ')).length, 1);
  } finally {
    Math.random = originalRandom;
  }
});

test('Flow execution cancellation releases the atomic guard for a later execution', async () => {
  await renderPage(<ExecutionCancellationHarness />);

  await act(async () => {
    click(buttonByText('Harness Execute'));
    click(buttonByText('Harness Cancel'));
    await settlePromises();
  });
  assert.equal(
    container?.querySelector('[data-testid="harness-execution-state"]')?.textContent,
    'idle',
  );

  await act(async () => {
    click(buttonByText('Harness Execute'));
    await settlePromises();
  });
  assert.equal(
    container?.querySelector('[data-testid="harness-execution-state"]')?.textContent,
    'executing',
  );

  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 900));
    await settlePromises();
  });
  assert.equal(
    container?.querySelector('[data-testid="harness-execution-state"]')?.textContent,
    'idle',
  );
});

test('Flows create completion preserves a newer user selection', async () => {
  const createResponse = deferred<Response>();
  const secondFlow: Flow = {
    id: 'selection-after-create',
    name: 'selection-after-create.flow.yaml',
    content: 'flow_id: selection-after-create\nsteps: []\n',
  };
  const createdFlow: Flow = {
    id: 'created-in-background',
    name: 'created-in-background.flow.yaml',
    content: '',
  };
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      if (method === 'POST') return createResponse.promise;
      if (path === '/api/panel/flows') {
        return Promise.resolve(successfulResponse(flowList([
          existingFlow,
          secondFlow,
          createdFlow,
        ])));
      }
      const flow = path.endsWith(`/${secondFlow.id}`) ? secondFlow : existingFlow;
      return Promise.resolve(successfulResponse(apiFlowDetail(flow)));
    },
    writable: true,
  });
  useAppStore.setState({flows: [{...existingFlow}, {...secondFlow}]});

  await renderPage(<FlowsPage />);
  await openFlowLibrary();
  await act(async () => {
    click(buttonByText('New Flow'));
    await settlePromises();
  });
  const nameInput = container?.querySelector<HTMLInputElement>(
    'input[placeholder^="Flow name"]',
  );
  assert.ok(nameInput);
  await act(async () => {
    changeInput(nameInput, 'created-in-background');
    click(buttonByText('Save'));
    await settlePromises();
  });
  await openFlowLibrary();
  await act(async () => {
    click(buttonByText(secondFlow.name));
    await settlePromises();
  });

  await act(async () => {
    createResponse.resolve(successfulResponse({
      created: true,
      filename: createdFlow.name,
      flow_id: createdFlow.id,
    }));
    await settlePromises();
  });
  assert.equal(container?.querySelector('h2')?.textContent, secondFlow.name);
  assert.match(container?.textContent ?? '', /flow_id:\s*selection-after-create/);
  assert.deepEqual(feedback, [{message: 'Flow created', type: 'success'}]);
});

test('Flows delete completion preserves a newer user selection and graph', async () => {
  const deleteResponse = deferred<Response>();
  const secondFlow: Flow = {
    id: 'selection-after-delete',
    name: 'selection-after-delete.flow.yaml',
    content: 'flow_id: selection-after-delete\nsteps: []\n',
  };
  let listCalls = 0;
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const method = init?.method ?? 'GET';
      const path = String(input);
      if (method === 'DELETE') return deleteResponse.promise;
      if (path === '/api/panel/flows') {
        listCalls += 1;
        return Promise.resolve(successfulResponse(flowList(
          listCalls === 1 ? [existingFlow, secondFlow] : [secondFlow],
        )));
      }
      const flow = path.endsWith(`/${secondFlow.id}`) ? secondFlow : existingFlow;
      return Promise.resolve(successfulResponse(apiFlowDetail(flow)));
    },
    writable: true,
  });
  useAppStore.setState({flows: [{...existingFlow}, {...secondFlow}]});

  await renderPage(
    <>
      <FlowsPage />
      <DialogContainerPage />
    </>,
  );
  await act(async () => {
    click(buttonByText('Delete'));
    await settlePromises();
  });
  await act(async () => {
    click(buttonsByText('Delete')[1]);
    await settlePromises();
  });
  await openFlowLibrary();
  await act(async () => {
    click(buttonByText(secondFlow.name));
    await settlePromises();
  });

  await act(async () => {
    deleteResponse.resolve(successfulResponse({deleted: true, flow_id: existingFlow.id}));
    await settlePromises();
  });
  assert.equal(container?.querySelector('h2')?.textContent, secondFlow.name);
  assert.match(container?.textContent ?? '', /flow_id:\s*selection-after-delete/);
  assert.deepEqual(feedback, [{message: 'Flow deleted', type: 'success'}]);
});
