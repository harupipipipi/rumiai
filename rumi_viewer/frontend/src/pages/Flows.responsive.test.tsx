import assert from 'node:assert/strict';
import test from 'node:test';
import {JSDOM} from 'jsdom';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';

import {useAppStore} from '@/src/store';
import {Flows} from './Flows';

const envelope = (data: unknown) => new Response(JSON.stringify({success: true, data, error: null}), {
  status: 200,
  headers: {'Content-Type': 'application/json'},
});

async function settle() {
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 20));
  });
}

test('Flows renders responsive drawer, wrapping actions, and bounded inspector in an 800px page', async () => {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', {url: 'http://localhost/flows'});
  Object.defineProperty(dom.window, 'innerWidth', {value: 800, configurable: true});
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    localStorage: dom.window.localStorage,
    sessionStorage: dom.window.sessionStorage,
    IS_REACT_ACT_ENVIRONMENT: true,
    ResizeObserver: class { observe() {} unobserve() {} disconnect() {} },
  });
  dom.window.requestAnimationFrame = callback => dom.window.setTimeout(() => callback(Date.now()), 0);
  dom.window.cancelAnimationFrame = id => dom.window.clearTimeout(id);
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/api/panel/flows')) {
      return envelope({flows: [{flow_id: 'demo', name: 'A very long translated flow title that must not hide primary actions', pack_id: 'defaultspack', filename: 'demo.flow.yaml'}], count: 1});
    }
    if (url.endsWith('/api/panel/flows/demo')) {
      return envelope({
        flow_id: 'demo', name: 'demo.flow.yaml', pack_id: 'defaultspack', filename: 'demo.flow.yaml',
        yaml_content: 'flow_id: demo\nname: Demo\nbase_pack: defaultspack\nsteps:\n  - id: start\n    type: trigger\n    position: {x: 10, y: 10}\n',
      });
    }
    throw new Error(`Unexpected request: ${url}`);
  }) as typeof fetch;
  useAppStore.setState({flows: [], isLoading: false, apiError: null, isSidebarOpen: true});

  let root: Root | undefined;
  await act(async () => {
    root = createRoot(document.getElementById('root')!);
    root.render(<Flows />);
  });
  await settle();
  assert.equal(useAppStore.getState().isSidebarOpen, false, 'the graph workspace gives the canvas priority');
  const editor = document.querySelector('[data-testid="flow-editor"]')!;
  assert.match(editor.className, /min-w-0/);
  const actions = document.querySelector('[data-testid="flow-actions"]')!;
  assert.match(actions.className, /flex-wrap/);

  const libraryToggle = document.querySelector('[data-testid="flow-library-toggle"]') as HTMLButtonElement;
  await act(async () => libraryToggle.click());
  const library = document.querySelector('[data-testid="flow-library"]')!;
  assert.match(library.className, /max-\[999px\]:absolute/);
  assert.doesNotMatch(document.documentElement.className, /overflow-x/);

  const node = document.querySelector('.react-flow__node') as HTMLElement | null;
  if (node) {
    await act(async () => node.click());
    const inspector = document.querySelector('[data-testid="flow-inspector"]')!;
    assert.match(inspector.className, /calc\(100%-4\.5rem\)/);
  }

  await act(async () => root?.unmount());
  dom.window.close();
});
