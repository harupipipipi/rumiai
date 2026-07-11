import assert from 'node:assert/strict';
import test from 'node:test';
import {JSDOM} from 'jsdom';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';

import type {ApiCapabilityGraph} from '@/src/lib/apiTypes';
import {GraphEditor} from './GraphEditor';

const graph = (id: string): ApiCapabilityGraph => ({
  graph_id: id,
  label: `Graph ${id}`,
  description_label: '',
  nodes: [],
  edges: [],
  metadata: {},
});

const envelope = (data: unknown, ok = true) => new Response(JSON.stringify({
  success: ok,
  data: ok ? data : null,
  error: ok ? null : data,
}), {status: ok ? 200 : 500, headers: {'Content-Type': 'application/json'}});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return {promise, resolve, reject};
}

async function settle() {
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0));
  });
}

test('GraphEditor commits selection only after detail fetch and ignores stale responses', async () => {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', {url: 'http://localhost/graphs'});
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    localStorage: dom.window.localStorage,
    sessionStorage: dom.window.sessionStorage,
    IS_REACT_ACT_ENVIRONMENT: true,
  });
  dom.window.confirm = () => true;

  const pendingB = deferred<Response>();
  const pendingC = deferred<Response>();
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/profiles')) {
      return envelope({profiles: [{
        profile_id: 'profile', label: 'Profile', description_label: '', permissions: {},
        enabled_nodes: [], disabled_nodes: [], node_settings: {}, policy: {},
      }], count: 1, startup_profile_relationship: {}});
    }
    if (url.endsWith('/graphs')) return envelope({graphs: [graph('A'), graph('B'), graph('C')], count: 3});
    if (url.endsWith('/graphs/B')) return pendingB.promise;
    if (url.endsWith('/graphs/C')) return pendingC.promise;
    throw new Error(`Unexpected request: ${url}`);
  }) as typeof fetch;

  let root: Root | undefined;
  await act(async () => {
    root = createRoot(document.getElementById('root')!);
    root.render(<GraphEditor />);
  });
  await settle();
  const selector = document.querySelectorAll('select')[1] as HTMLSelectElement;
  assert.equal(selector.value, 'A');

  await act(async () => {
    selector.value = 'B';
    selector.dispatchEvent(new dom.window.Event('change', {bubbles: true}));
    selector.value = 'C';
    selector.dispatchEvent(new dom.window.Event('change', {bubbles: true}));
  });
  assert.equal(selector.value, 'A', 'pending selection must not replace the loaded label');

  pendingC.resolve(envelope({graph: graph('C')}));
  await settle();
  assert.equal(selector.value, 'C');
  pendingB.resolve(envelope({graph: graph('B')}));
  await settle();
  assert.equal(selector.value, 'C', 'late B response must not roll the editor back');
  assert.match((document.querySelector('textarea') as HTMLTextAreaElement | null)?.value ?? document.body.textContent ?? '', /C/);

  await act(async () => root?.unmount());
  dom.window.close();
});

test('GraphEditor keeps the loaded resource locked after a rejected selection and retries it', async () => {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', {url: 'http://localhost/graphs'});
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    localStorage: dom.window.localStorage,
    sessionStorage: dom.window.sessionStorage,
    IS_REACT_ACT_ENVIRONMENT: true,
  });
  dom.window.confirm = () => true;
  let bAttempts = 0;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/profiles')) return envelope({profiles: [{profile_id: 'p', label: 'P', description_label: '', permissions: {}, enabled_nodes: [], disabled_nodes: [], node_settings: {}, policy: {}}], count: 1, startup_profile_relationship: {}});
    if (url.endsWith('/graphs')) return envelope({graphs: [graph('A'), graph('B')], count: 2});
    if (url.endsWith('/graphs/B')) {
      bAttempts += 1;
      return bAttempts === 1 ? envelope('B is unavailable', false) : envelope({graph: graph('B')});
    }
    throw new Error(`Unexpected request: ${url}`);
  }) as typeof fetch;

  let root: Root | undefined;
  await act(async () => {
    root = createRoot(document.getElementById('root')!);
    root.render(<GraphEditor />);
  });
  await settle();
  const selector = document.querySelectorAll('select')[1] as HTMLSelectElement;
  await act(async () => {
    selector.value = 'B';
    selector.dispatchEvent(new dom.window.Event('change', {bubbles: true}));
  });
  await settle();
  assert.equal(selector.value, 'A');
  assert.match(document.body.textContent ?? '', /B is unavailable/);
  const jsonTab = [...document.querySelectorAll('button')].find(button => button.textContent?.trim() === 'JSON')!;
  await act(async () => jsonTab.click());
  const save = [...document.querySelectorAll('button')].find(button => button.textContent?.includes('Save JSON'))!;
  assert.equal(save.hasAttribute('disabled'), false, 'the still-consistent A resource remains safe to save');
  const retry = [...document.querySelectorAll('button')].find(button => button.textContent?.includes('Retry'))!;
  await act(async () => retry.click());
  await settle();
  assert.equal(selector.value, 'B');

  await act(async () => root?.unmount());
  dom.window.close();
});

test('GraphEditor distinguishes a successful empty catalog from invalid graph JSON', async () => {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', {url: 'http://localhost/graphs'});
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    localStorage: dom.window.localStorage,
    sessionStorage: dom.window.sessionStorage,
    IS_REACT_ACT_ENVIRONMENT: true,
  });
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/profiles')) return envelope({profiles: [], count: 0, startup_profile_relationship: {}});
    if (url.endsWith('/graphs')) return envelope({graphs: [], count: 0});
    throw new Error(`Unexpected request: ${url}`);
  }) as typeof fetch;

  let root: Root | undefined;
  await act(async () => {
    root = createRoot(document.getElementById('root')!);
    root.render(<GraphEditor />);
  });
  await settle();
  assert.match(document.body.textContent ?? '', /No capability graphs/);
  assert.doesNotMatch(document.body.textContent ?? '', /Invalid JSON/);
  await act(async () => root?.unmount());
  dom.window.close();
});
