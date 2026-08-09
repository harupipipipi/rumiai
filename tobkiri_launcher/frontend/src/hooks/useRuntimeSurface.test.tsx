import assert from 'node:assert/strict';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {JSDOM} from 'jsdom';
import test from 'node:test';

import {
  broadcastRuntimeSurfaceRefresh,
  useRuntimeSurface,
  type RuntimeSurfaceClient,
} from './useRuntimeSurface';
import {RUNTIME_SURFACE_API_VERSION, type RuntimeSurfaceEnvelope, type RuntimeSurfaceId} from '@/src/lib/runtimeSurface';

const digest = (character: string): string => `sha256:${character.repeat(64)}`;

function envelope(surface: RuntimeSurfaceId): RuntimeSurfaceEnvelope<unknown> {
  return {
    runtime_surface_api_version: RUNTIME_SURFACE_API_VERSION,
    surface,
    state: 'ready',
    profile_id: 'defaults',
    profile_revision: digest('a'),
    plan_digest: digest('b'),
    catalog_revision: digest('c'),
    records: {
      profile_lock: {digest: digest('d'), source_ref: 'profile-lock-v4://defaults/lock'},
      resolved_plan: {digest: digest('b'), source_ref: 'resolved-plan-v1://defaults/plan'},
      activation_record: {digest: digest('1'), source_ref: 'activation-record-v1://defaults/activation'},
      authority_snapshot: {digest: digest('e'), source_ref: 'authority-snapshot-v4://defaults/snapshot'},
    },
    data: {},
  };
}

function createSurface(): {dom: JSDOM; container: HTMLElement; root: Root} {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>');
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

function SurfaceProbe({surface, client}: {surface: RuntimeSurfaceId; client: RuntimeSurfaceClient}) {
  const state = useRuntimeSurface(surface, client);
  return <span data-surface={surface}>{state.status}</span>;
}

test('activation refresh broadcast re-reads every mounted runtime surface', async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const {dom, container, root} = createSurface();
  const reads = {profile: 0, operations: 0};
  const profileClient: RuntimeSurfaceClient = {read: async <T,>() => { reads.profile += 1; return envelope('profile') as RuntimeSurfaceEnvelope<T>; }};
  const operationsClient: RuntimeSurfaceClient = {read: async <T,>() => { reads.operations += 1; return envelope('operations') as RuntimeSurfaceEnvelope<T>; }};
  try {
    await act(async () => {
      root.render(
        <>
          <SurfaceProbe surface="profile" client={profileClient} />
          <SurfaceProbe surface="operations" client={operationsClient} />
        </>,
      );
    });
    assert.deepEqual(reads, {profile: 1, operations: 1});
    await act(async () => { broadcastRuntimeSurfaceRefresh(); });
    assert.deepEqual(reads, {profile: 2, operations: 2});
  } finally {
    act(() => root.unmount());
    dom.window.close();
    Object.defineProperty(globalThis, 'window', {value: previousWindow, configurable: true});
    Object.defineProperty(globalThis, 'document', {value: previousDocument, configurable: true});
  }
});
