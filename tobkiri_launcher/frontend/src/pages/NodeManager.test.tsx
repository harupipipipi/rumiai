import assert from 'node:assert/strict';
import test from 'node:test';
import {JSDOM} from 'jsdom';
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';

import {
  buildCapabilityPackGroups,
  capabilityDomains,
  capabilityPackId,
  capabilityProfileForStartup,
  LatestRequestToken,
} from '../lib/nodeManagerCatalog';
import {useAppStore} from '../store';
import {NodeManager} from './NodeManager';

function envelope(data: unknown): Response {
  return new Response(JSON.stringify({success: true, data}), {
    headers: {'Content-Type': 'application/json'},
    status: 200,
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return {promise, reject, resolve};
}

async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

test('capabilityPackId uses Pack metadata before the node identifier fallback', () => {
  assert.equal(capabilityPackId({
    node_id: 'defaultspack.chat',
    kind: 'tool',
    ports: [],
    bindings: {},
    metadata: { pack_id: 'custom-pack' },
  }), 'custom-pack');

  assert.equal(capabilityPackId({
    node_id: 'defaultspack.chat',
    kind: 'tool',
    ports: [],
    bindings: {},
    metadata: {},
  }), 'defaultspack');
});

test('capabilityDomains normalizes domains declared by node metadata and requirements', () => {
  assert.deepEqual(capabilityDomains({
    node_id: 'defaultspack.browser',
    kind: 'tool',
    ports: [],
    bindings: {},
    metadata: { allowed_domains: ['example.com'] },
    requirements: { network: { domains: ['api.example.com', 'example.com'] } },
  }), ['api.example.com', 'example.com']);
});

test('capabilityProfileForStartup keeps Pack Nodes behind the startup profile bridge', () => {
  const startupProfile = {
    profile_id: 'defaults-profile',
    capability_profile_id: 'defaultspack.startup',
  } as never;
  const capabilityProfiles = [
    { profile_id: 'defaultspack.startup' },
    { profile_id: 'other.profile' },
  ] as never;

  assert.equal(
    capabilityProfileForStartup(startupProfile, capabilityProfiles),
    'defaultspack.startup',
  );
});

test('buildCapabilityPackGroups keeps large Pack catalogs grouped and counted in one pass', () => {
  const nodes = Array.from({length: 1_000}, (_, index) => ({
    node_id: `pack-${index % 5}.node-${index}`,
    kind: 'tool',
    ports: [],
    bindings: {},
    metadata: {pack_id: `pack-${index % 5}`},
    state: {
      node_id: `pack-${index % 5}.node-${index}`,
      installed: true,
      approved: true,
      enabled: index % 2 === 0,
      configured: true,
      status: index % 3 === 0 ? 'ready' : 'idle',
      missing: [],
    },
  }));

  const groups = buildCapabilityPackGroups(nodes);
  assert.equal(groups.length, 5);
  assert.deepEqual(
    groups.map((group) => [group.packId, group.nodes.length, group.enabledCount, group.readyCount]),
    [
      ['pack-0', 200, 100, 67],
      ['pack-1', 200, 100, 67],
      ['pack-2', 200, 100, 66],
      ['pack-3', 200, 100, 67],
      ['pack-4', 200, 100, 67],
    ],
  );
});

test('LatestRequestToken rejects an older response after a profile refresh begins', () => {
  const token = new LatestRequestToken();
  const first = token.begin();
  const second = token.begin();

  assert.equal(token.isCurrent(first), false);
  assert.equal(token.isCurrent(second), true);
  token.invalidate();
  assert.equal(token.isCurrent(second), false);
});

test('NodeManager ignores a late capability response after the user switches profiles again', async () => {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', {url: 'http://localhost/nodes'});
  Object.assign(globalThis, {
    document: dom.window.document,
    IS_REACT_ACT_ENVIRONMENT: true,
    localStorage: dom.window.localStorage,
    sessionStorage: dom.window.sessionStorage,
    window: dom.window,
  });
  useAppStore.setState({selectedStartupProfileId: ''});

  const pendingB = deferred<Response>();
  const pendingSecondA = deferred<Response>();
  let aNodeFetches = 0;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith('/startup/profiles')) {
      return envelope({
        active_profile_id: 'startup-a',
        profiles: [
          {profile_id: 'startup-a', name: 'Startup A', capability_profile_id: 'cap-a'},
          {profile_id: 'startup-b', name: 'Startup B', capability_profile_id: 'cap-b'},
        ],
      });
    }
    if (url.endsWith('/profiles')) {
      return envelope({
        profiles: [
          {profile_id: 'cap-a', label: 'Capability A'},
          {profile_id: 'cap-b', label: 'Capability B'},
        ],
      });
    }
    if (url.endsWith('/profiles/cap-a/nodes')) {
      aNodeFetches += 1;
      if (aNodeFetches === 1) {
        return envelope({nodes: [capabilityNode('pack-a.node', 'Node A')]});
      }
      return pendingSecondA.promise;
    }
    if (url.endsWith('/profiles/cap-b/nodes')) return pendingB.promise;
    throw new Error(`Unexpected request: ${url}`);
  }) as typeof fetch;

  let root: Root | undefined;
  await act(async () => {
    root = createRoot(document.getElementById('root')!);
    root.render(<NodeManager />);
  });
  await settle();
  await settle();

  const selector = document.querySelector('select[aria-label="Capability profile"]') as HTMLSelectElement;
  assert.equal(selector.value, 'startup-a');
  assert.match(document.body.textContent ?? '', /Node A/);

  await act(async () => {
    selector.value = 'startup-b';
    selector.dispatchEvent(new dom.window.Event('change', {bubbles: true}));
  });
  await settle();
  assert.equal(
    document.querySelector('button[role="switch"]')?.hasAttribute('disabled'),
    true,
    'nodes from the previous profile must not be actionable while the next profile loads',
  );

  await act(async () => {
    selector.value = 'startup-a';
    selector.dispatchEvent(new dom.window.Event('change', {bubbles: true}));
  });
  await settle();

  pendingSecondA.resolve(envelope({nodes: [capabilityNode('pack-a.fresh', 'Fresh A')]}));
  await settle();
  assert.match(document.body.textContent ?? '', /Fresh A/);

  pendingB.resolve(envelope({nodes: [capabilityNode('pack-b.node', 'Stale B')]}));
  await settle();
  assert.match(document.body.textContent ?? '', /Fresh A/);
  assert.doesNotMatch(document.body.textContent ?? '', /Stale B/);

  await act(async () => root?.unmount());
  dom.window.close();
});

function capabilityNode(nodeId: string, label: string) {
  return {
    bindings: {},
    kind: 'tool',
    label,
    metadata: {pack_id: 'pack-a'},
    node_id: nodeId,
    ports: [],
    state: {
      approved: true,
      configured: true,
      enabled: true,
      installed: true,
      missing: [],
      node_id: nodeId,
      status: 'ready',
    },
  };
}
